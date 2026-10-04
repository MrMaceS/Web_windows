"""
main.py
Точка входа FastAPI-приложения.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Depends, BackgroundTasks
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from assets import asset
from config import settings
from database import get_db, init_db, Lead
from schemas import (
    HeroFormLead,
    CalculatorLead,
    CalculatorEstimateRequest,
    CalculatorEstimateResponse,
    LeadResponse,
)
from logging_config import configure_logging
from middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from rate_limit import limiter
from pricing_service import PricingService, PricingError
import catalog_repository as catalog
import queue_client
from admin_auth import AdminAuthRequired, AdminForbidden, CsrfError
from admin_router import router as admin_router

configure_logging("DEBUG" if settings.environment == "development" else "INFO")
logger = logging.getLogger("main")

IS_PRODUCTION = settings.environment == "production"
DEFAULT_SESSION_SECRET = "dev-insecure-secret-change-me"

if IS_PRODUCTION and settings.admin_session_secret == DEFAULT_SESSION_SECRET:
    raise RuntimeError("ADMIN_SESSION_SECRET должен быть уникальным при ENVIRONMENT=production")

if IS_PRODUCTION:
    # Не роняем сайт из-за плейсхолдеров, но делаем их заметными в логах. Полный отчёт: python release_check.py
    import release_check

    for _item in release_check.check(settings)[0]:
        logger.warning("release-check [БЛОКЕР]: %s", _item)

app = FastAPI(
    title=f"{settings.company_name} — Лендинг установки окон",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

app.state.limiter = limiter

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.admin_session_secret,
    session_cookie="admin_session",
    max_age=settings.admin_session_max_age_seconds,
    same_site="lax",
    https_only=IS_PRODUCTION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# --- Jinja-хелперы для публичного frontend (не затрагивают API-контракты) ---

_STATIC_DIR = Path("static").resolve()

# TODO: заменить подписи на реальные и положить фото в static/images/portfolio/
PORTFOLIO_PROJECTS = (
    ("project-01", "Остекление балкона"),
    ("project-02", "Панорамное остекление лоджии"),
    ("project-03", "Замена окон в квартире"),
)


def _static_exists(url_path: str) -> bool:
    """True, если файл /static/... реально лежит на диске (защита от выхода за static/)."""
    if not url_path or not url_path.startswith("/static/"):
        return False
    target = (_STATIC_DIR / url_path[len("/static/"):]).resolve()
    return _STATIC_DIR in target.parents and target.is_file()


def _portfolio_items() -> list[dict]:
    items = []
    for slug, title in PORTFOLIO_PROJECTS:
        thumb = f"/static/images/portfolio/{slug}.webp"
        large = f"/static/images/portfolio/{slug}-large.webp"
        if _static_exists(thumb):
            items.append({
                "slug": slug,
                "title": title,
                "thumb": thumb,
                "large": large if _static_exists(large) else thumb,
            })
    return items


def _tel_href(value: str) -> str:
    """'+7 (900) 000-00-00' → 'tel:+79000000000' (валидная tel-ссылка без пробелов и скобок)."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return f"tel:+{digits}" if digits else "tel:"


templates.env.globals.update(
    asset=asset,
    static_exists=_static_exists,
    portfolio_items=_portfolio_items,
    current_year=lambda: datetime.now().year,
)
templates.env.filters["tel"] = _tel_href
app.include_router(admin_router)


@app.exception_handler(AdminAuthRequired)
async def admin_auth_required_handler(request: Request, exc: AdminAuthRequired):
    return RedirectResponse(url="/admin/login", status_code=303)


@app.exception_handler(AdminForbidden)
async def admin_forbidden_handler(request: Request, exc: AdminForbidden):
    return PlainTextResponse("Недостаточно прав для этого действия.", status_code=403)


@app.exception_handler(CsrfError)
async def csrf_error_handler(request: Request, exc: CsrfError):
    logger.warning("CSRF-проверка не пройдена для %s", request.url.path)
    return PlainTextResponse(
        "Форма устарела или отправлена не с этого сайта. Обновите страницу и попробуйте снова.",
        status_code=403,
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("Rate limit exceeded for path=%s", request.url.path)
    return JSONResponse(
        status_code=429,
        content={"success": False, "message": "Слишком много запросов. Попробуйте через минуту."},
    )


@app.exception_handler(PricingError)
async def pricing_error_handler(request: Request, exc: PricingError):
    logger.info("Pricing error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=422,
        content={"success": False, "message": str(exc)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            "pages/404.html",
            {"request": request, "settings": settings},
            status_code=404,
        )
    return JSONResponse(status_code=exc.status_code, content={"success": False, "message": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info("Validation error on %s", request.url.path)
    return JSONResponse(
        status_code=422,
        content={"success": False, "message": "Проверьте правильность заполнения формы."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Внутренняя ошибка сервера. Мы уже разбираемся."},
    )


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Приложение готово, environment=%s", settings.environment)


@app.on_event("shutdown")
async def on_shutdown():
    await queue_client.close_pool()


def get_or_head(path: str):
    """GET-маршрут, который отвечает и на HEAD (мониторинг доступности, краулеры, link-checkers).
    FastAPI по умолчанию для @app.get отдаёт на HEAD 405; тело для HEAD сервер отбрасывает сам."""
    return app.api_route(path, methods=["GET", "HEAD"])


@get_or_head("/health")
def health():
    return {"status": "ok"}


@get_or_head("/")
async def index(request: Request, db: Session = Depends(get_db)):
    root_categories = [
        {"category": c, "url": catalog.category_url(c)}
        for c in catalog.get_root_categories(db)
    ]
    return templates.TemplateResponse(
        "pages/home.html",
        {
            "request": request,
            "settings": settings,
            "root_categories": root_categories,
        },
    )


@get_or_head("/privacy")
async def privacy(request: Request):
    return templates.TemplateResponse(
        "pages/privacy.html",
        {"request": request, "settings": settings},
    )


def _calculator_link(window_type: str | None, profile_type: str | None) -> str | None:
    """Ссылка из карточки каталога на калькулятор с предзаполненными
    вариантом окна/профиля — калькулятор считывает эти query-параметры
    при загрузке (см. static/js/calculator.js)."""
    if not window_type or not profile_type:
        return None
    query = urlencode({"window_type": window_type, "profile_type": profile_type})
    return f"/?{query}#calculator"


def _build_product_card(db: Session, product) -> dict:
    price = catalog.get_product_price_from(db, product, settings.calculator_discount_percent)
    return {
        "product": product,
        "price": price,
        "calculator_link": _calculator_link(product.calculator_window_type, product.calculator_profile_type),
    }


@get_or_head("/sitemap.xml")
async def sitemap(request: Request, db: Session = Depends(get_db)):
    urls = [settings.domain + "/", settings.domain + "/privacy"]
    for category in catalog.get_all_active_categories(db):
        urls.append(settings.domain + catalog.category_url(category))

    body_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        body_lines.append(f"  <url><loc>{url}</loc></url>")
    body_lines.append("</urlset>")

    return Response(content="\n".join(body_lines), media_type="application/xml")


@get_or_head("/robots.txt")
async def robots():
    body = (
        "User-agent: *\n"
        "Disallow: /api/\n"
        f"Sitemap: {settings.domain}/sitemap.xml\n"
    )
    return PlainTextResponse(body)


@get_or_head("/{slug}/")
async def catalog_top_level(request: Request, slug: str, db: Session = Depends(get_db)):
    category = catalog.resolve_category_by_path(db, slug)
    if category is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    breadcrumbs = catalog.get_breadcrumbs(category)

    if category.children:
        child_categories = [
            {"category": child, "url": catalog.category_url(child)}
            for child in category.children
            if child.is_active
        ]
        return templates.TemplateResponse(
            "pages/catalog_category.html",
            {
                "request": request,
                "settings": settings,
                "category": category,
                "child_categories": child_categories,
                "breadcrumbs": breadcrumbs,
                "faq": category.faq_items(),
            },
        )

    products = catalog.get_products_for_category(db, category)
    product_cards = [_build_product_card(db, p) for p in products]
    similar = [
        {"category": c, "url": catalog.category_url(c)}
        for c in catalog.get_similar_categories(db, category)
    ]
    return templates.TemplateResponse(
        "pages/catalog_product.html",
        {
            "request": request,
            "settings": settings,
            "category": category,
            "product_cards": product_cards,
            "similar_categories": similar,
            "breadcrumbs": breadcrumbs,
            "faq": category.faq_items(),
        },
    )


@get_or_head("/{slug}/{child_slug}/")
async def catalog_child(request: Request, slug: str, child_slug: str, db: Session = Depends(get_db)):
    category = catalog.resolve_category_by_path(db, slug, child_slug)
    if category is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    breadcrumbs = catalog.get_breadcrumbs(category)
    products = catalog.get_products_for_category(db, category)
    product_cards = [_build_product_card(db, p) for p in products]
    similar = [
        {"category": c, "url": catalog.category_url(c)}
        for c in catalog.get_similar_categories(db, category)
    ]
    return templates.TemplateResponse(
        "pages/catalog_product.html",
        {
            "request": request,
            "settings": settings,
            "category": category,
            "product_cards": product_cards,
            "similar_categories": similar,
            "breadcrumbs": breadcrumbs,
            "faq": category.faq_items(),
        },
    )


def _save_lead(db: Session, lead_dict: dict, source: str) -> Lead:
    """Сохраняет лид в БД. Honeypot-поле 'website' не сохраняется — это
    техническая ловушка для ботов, а не бизнес-данные."""
    lead_dict = dict(lead_dict)
    lead_dict.pop("website", None)
    consent = lead_dict.pop("consent")

    lead_dict["source"] = source
    lead_dict["consent_given"] = consent

    db_lead = Lead(**lead_dict)
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead


def _is_bot(payload: dict) -> bool:
    """Honeypot-проверка: настоящие пользователи не видят и не заполняют
    поле 'website' (скрыто через CSS в partials/forms.html)."""
    return bool(payload.get("website"))


@app.post("/api/lead", response_model=LeadResponse)
@limiter.limit(settings.rate_limit_lead)
async def create_hero_lead(
    request: Request,
    lead: HeroFormLead,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Приём заявки с форм 'Вызвать замерщика' / 'Заказать звонок'."""
    payload = lead.model_dump()
    if _is_bot(payload):
        return LeadResponse(success=True, message="Заявка принята.", lead_id=0)

    source = payload.pop("source", "hero_form")
    db_lead = _save_lead(db, payload, source=source)
    background_tasks.add_task(
        queue_client.enqueue_telegram_job, db_lead.id, {**payload, "id": db_lead.id, "source": source}
    )

    return LeadResponse(
        success=True,
        message="Спасибо! Замерщик свяжется с вами в течение 15 минут.",
        lead_id=db_lead.id,
    )


@app.post("/api/v1/calculator/estimate", response_model=CalculatorEstimateResponse)
@limiter.limit(settings.rate_limit_estimate)
async def calculator_estimate(
    request: Request,
    payload: CalculatorEstimateRequest,
    db: Session = Depends(get_db),
):
    """
    Sprint 2. Предварительный расчёт стоимости БЕЗ создания заявки —
    вызывается на шаге 3 → 4 калькулятора, чтобы показать цену до того,
    как пользователь оставит телефон. Не пишет ничего в БД (кроме чтения
    price_rules) и не уходит в Telegram — это чисто витринный расчёт.
    Сама заявка (с окончательным пересчётом той же формулой) создаётся
    отдельным вызовом /api/calculator-lead.
    """
    pricing = PricingService(db, discount_percent=settings.calculator_discount_percent)
    breakdown = pricing.estimate(
        window_type=payload.window_type,
        profile_type=payload.profile_type,
        width_mm=payload.width_mm,
        height_mm=payload.height_mm,
        quantity=payload.quantity,
    )
    return CalculatorEstimateResponse(
        area_m2=breakdown.area_m2,
        base_price=breakdown.base_price,
        multiplier=breakdown.multiplier,
        subtotal=breakdown.subtotal,
        discount_percent=breakdown.discount_percent,
        discount_amount=breakdown.discount_amount,
        total_price=breakdown.total_price,
        currency=breakdown.currency,
    )


@app.post("/api/calculator-lead", response_model=LeadResponse)
@limiter.limit(settings.rate_limit_lead)
async def create_calculator_lead(
    request: Request,
    lead: CalculatorLead,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Приём заявки с последнего шага калькулятора.

    Sprint 2: цена больше НЕ берётся из тела запроса. Сервер независимо
    пересчитывает её через тот же PricingService, что и /estimate —
    итоговая calculated_price в БД всегда серверная. Если клиент прислал
    своё (устаревшее или подделанное) значение calculated_price, оно
    используется только для лог-сравнения на предмет расхождения —
    не для сохранения и не для суммы в сообщении менеджеру.
    """
    payload = lead.model_dump()
    if _is_bot(payload):
        return LeadResponse(success=True, message="Заявка принята.", lead_id=0)

    client_reported_price = payload.pop("calculated_price", None)

    pricing = PricingService(db, discount_percent=settings.calculator_discount_percent)
    breakdown = pricing.estimate(
        window_type=payload["window_type"],
        profile_type=payload["profile_type"],
        width_mm=payload["width_mm"],
        height_mm=payload["height_mm"],
        quantity=payload["quantity"],
    )

    if client_reported_price is not None and abs(client_reported_price - breakdown.total_price) > 1:
        logger.warning(
            "Calculator price mismatch: client=%s server=%s",
            client_reported_price,
            breakdown.total_price,
        )

    payload["calculated_price"] = breakdown.total_price
    payload["calculator_config_json"] = breakdown.to_json()

    db_lead = _save_lead(db, payload, source="calculator")
    background_tasks.add_task(
        queue_client.enqueue_telegram_job, db_lead.id, {**payload, "id": db_lead.id, "source": "calculator"}
    )

    return LeadResponse(
        success=True,
        message=(
            f"Ваш расчёт (~{breakdown.total_price:.0f} ₽) отправлен менеджеру. "
            f"Мы перезвоним и зафиксируем скидку {settings.calculator_discount_percent}%!"
        ),
        lead_id=db_lead.id,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
