"""
admin_router.py
Sprint 4. Защищённая админка: аутентификация по сессии, RBAC (admin/manager),
управление ценами и каталогом, работа с заявками (статус, ретрай Telegram),
журнал аудита, дашборд по лидам/UTM.
"""

import json
import math
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from assets import asset
from config import settings
from database import (
    get_db,
    Lead,
    AdminUser,
    PriceRule,
    Category,
    Product,
    ProductOption,
    ProductImage,
    AuditLog,
)
from admin_auth import get_current_admin_optional, require_role, verify_csrf, get_or_create_csrf_token
from security import hash_password, verify_password
from audit import record_audit
from rate_limit import limiter
import queue_client
from telegram_delivery import lead_to_notification_dict

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")
templates.env.globals["asset"] = asset

PAGE_SIZE = 25


def render(request: Request, template: str, context: dict, status_code: int = 200):
    context = {
        "request": request,
        "settings": settings,
        "csrf_token": get_or_create_csrf_token(request),
        **context,
    }
    return templates.TemplateResponse(template, context, status_code=status_code)


@router.get("/login")
async def login_form(request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin_optional(request, db)
    if admin is not None:
        return RedirectResponse(url="/admin/", status_code=303)
    return render(request, "admin/login.html", {"admin": None})


@router.post("/login")
@limiter.limit("10/minute")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return render(
            request, "admin/login.html",
            {"admin": None, "error": "Неверный логин или пароль."},
            status_code=401,
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    request.session.clear()
    request.session["admin_user_id"] = user.id
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("/")
async def dashboard(request: Request, admin: AdminUser = Depends(require_role("admin", "manager")), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    period_start = today_start - timedelta(days=14)

    all_leads = db.query(Lead).filter(Lead.created_at >= period_start).all()

    totals = {
        "total": db.query(Lead).count(),
        "today": sum(1 for lead in all_leads if lead.created_at and lead.created_at.replace(tzinfo=timezone.utc) >= today_start),
        "week": sum(1 for lead in all_leads if lead.created_at and lead.created_at.replace(tzinfo=timezone.utc) >= week_start),
    }

    by_source = Counter(lead.source for lead in all_leads)
    by_manager_status = Counter(lead.manager_status for lead in all_leads)
    by_telegram_status = Counter(lead.telegram_status for lead in all_leads)

    by_day: dict[str, int] = {}
    for i in range(14):
        day = (today_start - timedelta(days=13 - i)).strftime("%d.%m")
        by_day[day] = 0
    for lead in all_leads:
        if lead.created_at:
            day = lead.created_at.replace(tzinfo=timezone.utc).strftime("%d.%m")
            if day in by_day:
                by_day[day] += 1

    utm_counter = Counter(
        (lead.utm_source or "—", lead.utm_campaign or "—")
        for lead in all_leads
        if lead.utm_source or lead.utm_campaign
    )
    top_utm = utm_counter.most_common(10)

    return render(request, "admin/dashboard.html", {
        "admin": admin,
        "totals": totals,
        "by_source": by_source.most_common(),
        "by_manager_status": by_manager_status.most_common(),
        "by_telegram_status": by_telegram_status.most_common(),
        "by_day": list(by_day.items()),
        "top_utm": top_utm,
    })


@router.get("/leads")
async def leads_list(
    request: Request,
    admin: AdminUser = Depends(require_role("admin", "manager")),
    db: Session = Depends(get_db),
    source: Optional[str] = None,
    telegram_status: Optional[str] = None,
    manager_status: Optional[str] = None,
    page: int = 1,
):
    query = db.query(Lead)
    if source:
        query = query.filter(Lead.source == source)
    if telegram_status:
        query = query.filter(Lead.telegram_status == telegram_status)
    if manager_status:
        query = query.filter(Lead.manager_status == manager_status)

    total = query.count()
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))

    leads = (
        query.order_by(Lead.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )

    return render(request, "admin/leads_list.html", {
        "admin": admin,
        "leads": leads,
        "filters": {"source": source or "", "telegram_status": telegram_status or "", "manager_status": manager_status or ""},
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.get("/leads/{lead_id}")
async def lead_detail(request: Request, lead_id: int, admin: AdminUser = Depends(require_role("admin", "manager")), db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead is None:
        return render(request, "admin/leads_list.html", {"admin": admin, "leads": [], "filters": {}, "page": 1, "total_pages": 1, "total": 0, "error": "Заявка не найдена"})

    config = None
    if lead.calculator_config_json:
        try:
            config = json.loads(lead.calculator_config_json)
        except ValueError:
            config = None

    return render(request, "admin/lead_detail.html", {"admin": admin, "lead": lead, "config": config})


@router.post("/leads/{lead_id}/status")
async def lead_update_status(
    request: Request,
    lead_id: int,
    manager_status: str = Form(...),
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin", "manager")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead is None:
        return RedirectResponse(url="/admin/leads", status_code=303)

    allowed = {"new", "contacted", "closed"}
    if manager_status not in allowed:
        return RedirectResponse(url=f"/admin/leads/{lead_id}", status_code=303)

    before = {"manager_status": lead.manager_status}
    lead.manager_status = manager_status
    record_audit(db, admin, "lead.status_change", "lead", lead_id, before, {"manager_status": manager_status})
    db.commit()

    return RedirectResponse(url=f"/admin/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/retry-telegram")
async def lead_retry_telegram(
    request: Request,
    lead_id: int,
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin", "manager")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead is None:
        return RedirectResponse(url="/admin/leads", status_code=303)

    record_audit(db, admin, "lead.retry_telegram", "lead", lead_id, {"telegram_status": lead.telegram_status}, None)
    db.commit()

    await queue_client.enqueue_telegram_job(lead.id, lead_to_notification_dict(lead))

    return RedirectResponse(url=f"/admin/leads/{lead_id}", status_code=303)


@router.get("/price-rules")
async def price_rules_list(request: Request, admin: AdminUser = Depends(require_role("admin")), db: Session = Depends(get_db)):
    rules = db.query(PriceRule).order_by(PriceRule.category, PriceRule.sort_order).all()
    window_rules = [r for r in rules if r.category == "window_type"]
    profile_rules = [r for r in rules if r.category == "profile"]
    return render(request, "admin/price_rules.html", {"admin": admin, "window_rules": window_rules, "profile_rules": profile_rules})


@router.post("/price-rules/{rule_id}")
async def price_rule_update(
    request: Request,
    rule_id: int,
    value: float = Form(...),
    is_active: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    rule = db.query(PriceRule).filter(PriceRule.id == rule_id).first()
    if rule is None:
        return RedirectResponse(url="/admin/price-rules", status_code=303)

    before = {"value": rule.value, "is_active": rule.is_active}
    rule.value = value
    rule.is_active = is_active == "on"
    after = {"value": rule.value, "is_active": rule.is_active}
    record_audit(db, admin, "price_rule.update", "price_rule", rule_id, before, after)
    db.commit()

    return RedirectResponse(url="/admin/price-rules", status_code=303)


@router.get("/catalog/categories")
async def categories_list(request: Request, admin: AdminUser = Depends(require_role("admin")), db: Session = Depends(get_db)):
    categories = db.query(Category).options(joinedload(Category.parent)).order_by(Category.parent_id.is_(None).desc(), Category.sort_order).all()
    return render(request, "admin/categories_list.html", {"admin": admin, "categories": categories})


@router.get("/catalog/categories/{category_id}")
async def category_edit_form(request: Request, category_id: int, admin: AdminUser = Depends(require_role("admin")), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        return RedirectResponse(url="/admin/catalog/categories", status_code=303)
    return render(request, "admin/category_edit.html", {"admin": admin, "category": category})


@router.post("/catalog/categories/{category_id}")
async def category_edit_submit(
    request: Request,
    category_id: int,
    name: str = Form(...),
    short_description: str = Form(""),
    description_html: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    is_active: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        return RedirectResponse(url="/admin/catalog/categories", status_code=303)

    before = {
        "name": category.name, "short_description": category.short_description,
        "meta_title": category.meta_title, "is_active": category.is_active,
    }
    category.name = name
    category.short_description = short_description or None
    category.description_html = description_html or None
    category.meta_title = meta_title or None
    category.meta_description = meta_description or None
    category.is_active = is_active == "on"
    category.updated_at = datetime.now(timezone.utc)

    after = {
        "name": category.name, "short_description": category.short_description,
        "meta_title": category.meta_title, "is_active": category.is_active,
    }
    record_audit(db, admin, "category.update", "category", category_id, before, after)
    db.commit()

    return RedirectResponse(url=f"/admin/catalog/categories/{category_id}", status_code=303)


@router.get("/catalog/products")
async def products_list(request: Request, admin: AdminUser = Depends(require_role("admin")), db: Session = Depends(get_db), category_id: Optional[int] = None):
    query = db.query(Product).options(joinedload(Product.category))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    products = query.order_by(Product.category_id, Product.sort_order).all()
    categories = db.query(Category).order_by(Category.name).all()
    return render(request, "admin/products_list.html", {"admin": admin, "products": products, "categories": categories, "selected_category_id": category_id})


@router.get("/catalog/products/{product_id}")
async def product_edit_form(request: Request, product_id: int, admin: AdminUser = Depends(require_role("admin")), db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(joinedload(Product.options), joinedload(Product.images), joinedload(Product.category))
        .filter(Product.id == product_id)
        .first()
    )
    if product is None:
        return RedirectResponse(url="/admin/catalog/products", status_code=303)

    window_type_labels = [r.label for r in db.query(PriceRule).filter(PriceRule.category == "window_type", PriceRule.is_active.is_(True)).all()]
    profile_labels = [r.label for r in db.query(PriceRule).filter(PriceRule.category == "profile", PriceRule.is_active.is_(True)).all()]

    return render(request, "admin/product_edit.html", {
        "admin": admin, "product": product,
        "window_type_labels": window_type_labels, "profile_labels": profile_labels,
    })


@router.post("/catalog/products/{product_id}")
async def product_edit_submit(
    request: Request,
    product_id: int,
    name: str = Form(...),
    short_description: str = Form(""),
    description_html: str = Form(""),
    calculator_window_type: str = Form(""),
    calculator_profile_type: str = Form(""),
    is_active: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        return RedirectResponse(url="/admin/catalog/products", status_code=303)

    before = {
        "name": product.name, "calculator_window_type": product.calculator_window_type,
        "calculator_profile_type": product.calculator_profile_type, "is_active": product.is_active,
    }
    product.name = name
    product.short_description = short_description or None
    product.description_html = description_html or None
    product.calculator_window_type = calculator_window_type or None
    product.calculator_profile_type = calculator_profile_type or None
    product.is_active = is_active == "on"
    product.updated_at = datetime.now(timezone.utc)

    after = {
        "name": product.name, "calculator_window_type": product.calculator_window_type,
        "calculator_profile_type": product.calculator_profile_type, "is_active": product.is_active,
    }
    record_audit(db, admin, "product.update", "product", product_id, before, after)
    db.commit()

    return RedirectResponse(url=f"/admin/catalog/products/{product_id}", status_code=303)


@router.post("/catalog/products/{product_id}/options/add")
async def product_option_add(
    request: Request,
    product_id: int,
    group_label: str = Form(...),
    value_label: str = Form(...),
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    max_sort = db.query(ProductOption).filter(ProductOption.product_id == product_id).count()
    option = ProductOption(product_id=product_id, group_label=group_label, value_label=value_label, sort_order=max_sort)
    db.add(option)
    db.flush()
    record_audit(db, admin, "product_option.add", "product_option", option.id, None, {"group_label": group_label, "value_label": value_label})
    db.commit()
    return RedirectResponse(url=f"/admin/catalog/products/{product_id}", status_code=303)


@router.post("/catalog/products/{product_id}/options/{option_id}/delete")
async def product_option_delete(
    request: Request,
    product_id: int,
    option_id: int,
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    option = db.query(ProductOption).filter(ProductOption.id == option_id, ProductOption.product_id == product_id).first()
    if option is not None:
        record_audit(db, admin, "product_option.delete", "product_option", option_id, {"group_label": option.group_label, "value_label": option.value_label}, None)
        db.delete(option)
        db.commit()
    return RedirectResponse(url=f"/admin/catalog/products/{product_id}", status_code=303)


@router.post("/catalog/products/{product_id}/images/add")
async def product_image_add(
    request: Request,
    product_id: int,
    image_path: str = Form(...),
    alt_text: str = Form(...),
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    max_sort = db.query(ProductImage).filter(ProductImage.product_id == product_id).count()
    image = ProductImage(product_id=product_id, image_path=image_path, alt_text=alt_text, sort_order=max_sort, is_primary=(max_sort == 0))
    db.add(image)
    db.flush()
    record_audit(db, admin, "product_image.add", "product_image", image.id, None, {"image_path": image_path, "alt_text": alt_text})
    db.commit()
    return RedirectResponse(url=f"/admin/catalog/products/{product_id}", status_code=303)


@router.post("/catalog/products/{product_id}/images/{image_id}/delete")
async def product_image_delete(
    request: Request,
    product_id: int,
    image_id: int,
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    image = db.query(ProductImage).filter(ProductImage.id == image_id, ProductImage.product_id == product_id).first()
    if image is not None:
        record_audit(db, admin, "product_image.delete", "product_image", image_id, {"image_path": image.image_path}, None)
        db.delete(image)
        db.commit()
    return RedirectResponse(url=f"/admin/catalog/products/{product_id}", status_code=303)


@router.get("/users")
async def users_list(request: Request, admin: AdminUser = Depends(require_role("admin")), db: Session = Depends(get_db)):
    users = db.query(AdminUser).order_by(AdminUser.created_at).all()
    return render(request, "admin/users_list.html", {"admin": admin, "users": users})


@router.post("/users/create")
async def user_create(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("manager"),
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    role = role if role in {"admin", "manager"} else "manager"
    existing = db.query(AdminUser).filter(AdminUser.username == username).first()
    if existing is not None:
        users = db.query(AdminUser).order_by(AdminUser.created_at).all()
        return render(request, "admin/users_list.html", {"admin": admin, "users": users, "error": "Такой логин уже существует."})

    user = AdminUser(username=username, password_hash=hash_password(password), role=role, is_active=True)
    db.add(user)
    db.flush()
    record_audit(db, admin, "admin_user.create", "admin_user", user.id, None, {"username": username, "role": role})
    db.commit()

    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/deactivate")
async def user_deactivate(
    request: Request,
    user_id: int,
    csrf_token: str = Form(...),
    admin: AdminUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if user is not None and user.id != admin.id:
        record_audit(db, admin, "admin_user.deactivate", "admin_user", user_id, {"is_active": True}, {"is_active": False})
        user.is_active = False
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/audit")
async def audit_log_view(request: Request, admin: AdminUser = Depends(require_role("admin")), db: Session = Depends(get_db), page: int = 1):
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    total = query.count()
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    entries = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    return render(request, "admin/audit_log.html", {"admin": admin, "entries": entries, "page": page, "total_pages": total_pages})
