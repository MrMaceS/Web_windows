"""
release_check.py — проверка «готов ли сайт к публикации».

Запуск (перед деплоем / в CI):
    python release_check.py              # код выхода 1, если есть блокеры
    docker compose run --rm app python release_check.py

Что проверяется и почему так:
* Бизнес-поля (название, телефон, адрес, домен, размер скидки) должны быть ЯВНО заданы в .env.
  Сравнивать с демо-строками хрупко (кто-то поменял одну цифру в плейсхолдере — и проверка «прошла»);
  pydantic помнит, какие поля пришли из окружения (model_fields_set), этим и пользуемся.
* Скидка калькулятора реально применяется к ценам и обещается клиенту в ответе формы, поэтому её нельзя
  оставлять «по умолчанию»: это выдуманная скидка.
* Видимые TODO в публичных шаблонах (текст политики конфиденциальности) — блокер: это юридический текст.

Приложение при старте в production пишет эти же блокеры в лог (WARNING), но не падает.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"

# поля, которые обязаны прийти из .env (а не из демо-значений в config.py)
MUST_BE_EXPLICIT = {
    "company_name": "название компании (видно в шапке, title, JSON-LD)",
    "company_phone": "телефон (шапка, кнопки «Позвонить», JSON-LD)",
    "company_address": "адрес (контакты, JSON-LD)",
    "domain": "домен с https:// (canonical, sitemap, og:url)",
    "calculator_discount_percent": "размер скидки: применяется к ценам и обещается клиенту — подтвердите реальную",
}
DEFAULT_DB_PASSWORD = "window_pass"


def _strip_comments(src: str) -> str:
    src = re.sub(r"\{#.*?#\}", "", src, flags=re.S)  # комментарии Jinja
    return re.sub(r"<!--.*?-->", "", src, flags=re.S)  # HTML-комментарии


def visible_todos() -> list[str]:
    """TODO/заглушки в публичных шаблонах вне комментариев (админка не в счёт)."""
    found = []
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        if "admin" in tpl.relative_to(TEMPLATES).parts:
            continue
        text = _strip_comments(tpl.read_text(encoding="utf-8"))
        for n, line in enumerate(text.splitlines(), 1):
            if re.search(r"TODO|ЗАГЛУШК|lorem ipsum", line, re.I):
                found.append(f"{tpl.relative_to(ROOT)}: {line.strip()[:80]}")
    return found


def has_og_image() -> bool:
    base = _strip_comments((TEMPLATES / "base.html").read_text(encoding="utf-8"))
    return bool(re.search(r"<meta[^>]+og:image", base))


def check(settings) -> tuple[list[str], list[str]]:
    """Возвращает (блокеры, предупреждения)."""
    blockers: list[str] = []
    warnings: list[str] = []
    explicit = settings.model_fields_set

    if settings.environment != "production":
        blockers.append(f"ENVIRONMENT={settings.environment!r}, для публикации нужен 'production'")

    for field, why in MUST_BE_EXPLICIT.items():
        if field not in explicit:
            blockers.append(f"{field.upper()} не задан в .env (используется демо-значение): {why}")

    # Значение задано явно, но совпадает с демо-значением из config.py (типично: cp .env.example .env и забыли).
    # Скидку не сравниваем: 15% может быть реальным решением владельца, для неё достаточно явной заданности.
    for field in ("company_name", "company_phone", "company_address"):
        demo = type(settings).model_fields[field].default
        if field in explicit and getattr(settings, field) == demo:
            blockers.append(f"{field.upper()}={demo!r} — это демо-значение, замените на реальное")

    if "domain" in explicit:
        d = settings.domain
        if not d.startswith("https://") or "example." in d or d.endswith("/"):
            blockers.append(f"DOMAIN={d!r}: нужен реальный адрес вида https://ваш-домен.ru (без слэша в конце)")

    if "company_phone" in explicit and len(re.sub(r"\D", "", settings.company_phone)) < 11:
        blockers.append(f"COMPANY_PHONE={settings.company_phone!r}: похоже на неполный номер")

    secret = settings.admin_session_secret
    if secret == "dev-insecure-secret-change-me" or len(secret) < 32:
        blockers.append("ADMIN_SESSION_SECRET: дефолтный или короче 32 символов")

    if DEFAULT_DB_PASSWORD in settings.database_url:
        blockers.append("DATABASE_URL использует демо-пароль БД (window_pass)")

    origins = settings.allowed_origins_list
    if any("localhost" in o or "127.0.0.1" in o for o in origins):
        blockers.append("ALLOWED_ORIGINS содержит localhost — укажите боевой домен")
    elif "domain" in explicit and settings.domain not in origins:
        warnings.append(f"ALLOWED_ORIGINS не содержит {settings.domain}")

    todos = visible_todos()
    if todos:
        blockers.append(f"В публичных шаблонах {len(todos)} видимых TODO (текст политики конфиденциальности): {todos[0]}")

    if not settings.legal_entity_name:
        warnings.append("LEGAL_ENTITY_NAME пуст: в футере и политике нет реквизитов (ООО/ИП, ИНН, ОГРН)")
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        warnings.append("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы: заявки сохраняются, но уведомления не придут")
    if not settings.redis_url:
        warnings.append("REDIS_URL пуст: очередь доставки уведомлений недоступна")
    if not has_og_image():
        warnings.append("нет og:image: у ссылок в мессенджерах и соцсетях не будет картинки")
    if not settings.yandex_metrika_id:
        warnings.append("YANDEX_METRIKA_ID пуст: аналитика выключена (если так и задумано — игнорируйте)")

    return blockers, warnings


def main() -> int:
    from config import settings

    blockers, warnings = check(settings)
    print("Проверка релиза\n")
    for b in blockers:
        print(f"  [БЛОКЕР]       {b}")
    for w in warnings:
        print(f"  [предупреждение] {w}")
    if not blockers and not warnings:
        print("  Всё в порядке.")
    print(f"\nБлокеров: {len(blockers)}, предупреждений: {len(warnings)}")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
