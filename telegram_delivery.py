"""
telegram_delivery.py
Единая функция "отправить уведомление о лиде в Telegram и записать
результат в БД" — используется в трёх местах:
  1. inline-режим без Redis (queue_client.py, поведение Sprint 1-3);
  2. задача ARQ-воркера (worker.py, Sprint 4);
  3. кнопка "Отправить повторно" в админке (admin_router.py).
Вынесена отдельно, чтобы подсчёт попыток и запись статуса не разъехались
между этими тремя вызывающими местами.
"""

import logging
from datetime import datetime, timezone

from database import SessionLocal, Lead
from bot import send_lead_to_telegram

logger = logging.getLogger("telegram_delivery")


async def deliver_and_record(lead_id: int, lead_dict: dict) -> bool:
    success = await send_lead_to_telegram(lead_dict)

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead is None:
            logger.warning("deliver_and_record: lead_id=%s не найден в БД", lead_id)
            return success
        lead.telegram_attempts = (lead.telegram_attempts or 0) + 1
        lead.telegram_last_attempt_at = datetime.now(timezone.utc)
        lead.telegram_status = "sent" if success else "failed"
        lead.telegram_error = None if success else "Не удалось отправить уведомление в Telegram"
        db.commit()
    finally:
        db.close()

    return success


def lead_to_notification_dict(lead: Lead) -> dict:
    """Собирает payload для send_lead_to_telegram из строки Lead — нужен
    и воркеру (sweep неудачных заявок), и ручному ретраю из админки, где
    под рукой уже готовый объект Lead, а не свежий payload из формы."""
    return {
        "id": lead.id,
        "name": lead.name,
        "phone": lead.phone,
        "source": lead.source,
        "window_type": lead.window_type,
        "profile_type": lead.profile_type,
        "width_mm": lead.width_mm,
        "height_mm": lead.height_mm,
        "quantity": lead.quantity,
        "calculated_price": lead.calculated_price,
        "comment": lead.comment,
        "utm_source": lead.utm_source,
        "utm_medium": lead.utm_medium,
        "utm_campaign": lead.utm_campaign,
    }
