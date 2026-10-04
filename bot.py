"""
bot.py
Асинхронная отправка лида менеджеру в Telegram через httpx (Bot API),
без тяжёлого aiogram — для одностороннего оповещения он избыточен.
"""

import html
import logging

import httpx

from config import settings

logger = logging.getLogger("bot")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _e(value) -> str:
    """HTML-экранирование пользовательского ввода перед вставкой в сообщение
    с parse_mode=HTML — иначе, например, символ '<' в имени лида ломает
    разметку и Telegram отклоняет весь запрос (400 Bad Request)."""
    return html.escape(str(value))


def _format_lead_message(lead: dict) -> str:
    """Формирует читаемое сообщение для менеджера."""
    lines = [f"🔔 <b>Новая заявка — {_e(lead.get('source', 'сайт'))}</b>", ""]

    if lead.get("name"):
        lines.append(f"👤 Имя: {_e(lead['name'])}")
    lines.append(f"📞 Телефон: <code>{_e(lead['phone'])}</code>")

    if lead.get("window_type"):
        lines.append("")
        lines.append("<b>Данные калькулятора:</b>")
        lines.append(f"— Тип: {_e(lead['window_type'])}")
        lines.append(f"— Профиль: {_e(lead['profile_type'])}")
        lines.append(f"— Размер: {lead['width_mm']}×{lead['height_mm']} мм")
        lines.append(f"— Количество: {lead['quantity']}")
        lines.append(f"— Расчётная цена: ~{lead['calculated_price']:.0f} ₽")

    if lead.get("comment"):
        lines.append("")
        lines.append(f"💬 Комментарий: {_e(lead['comment'])}")

    utm_parts = [
        f"{k}={_e(v)}"
        for k, v in (
            ("source", lead.get("utm_source")),
            ("medium", lead.get("utm_medium")),
            ("campaign", lead.get("utm_campaign")),
        )
        if v
    ]
    if utm_parts:
        lines.append("")
        lines.append(f"📊 UTM: {', '.join(utm_parts)}")

    return "\n".join(lines)


async def send_lead_to_telegram(lead: dict) -> bool:
    """
    Отправляет заявку в Telegram-чат менеджеров.
    Вызывается через BackgroundTasks в main.py — то есть НЕ блокирует
    ответ пользователю. Пользователь мгновенно видит "Спасибо!",
    даже если Telegram API в этот момент подтормаживает.
    Ошибки логируются, но не роняют запрос — заявка уже сохранена в БД
    и не потеряется, даже если Telegram недоступен.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram не настроен (нет токена/chat_id) — уведомление пропущено")
        return False

    url = TELEGRAM_API_URL.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": _format_lead_message(lead),
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        # НЕ логируем str(exc)/exc.request.url: httpx включает в них полный
        # URL запроса, а URL Telegram Bot API содержит токен бота в пути
        # (/bot<TOKEN>/sendMessage) — иначе секрет утечёт в логи приложения.
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.error("Не удалось отправить лид в Telegram: %s (status=%s)", type(exc).__name__, status)
        return False
