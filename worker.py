"""
worker.py
ARQ-воркер (Sprint 4): доставка уведомлений в Telegram с экспоненциальным
backoff-ретраем + периодический sweep заявок, застрявших в telegram_status
='failed' (на случай, если отложенная задача потерялась при рестарте
воркера — cron подхватит их отдельно).
"""

import logging
from datetime import datetime, timezone, timedelta

from arq import cron
from arq.connections import RedisSettings

from config import settings
from database import SessionLocal, Lead
from telegram_delivery import deliver_and_record, lead_to_notification_dict
from logging_config import configure_logging

configure_logging("INFO")
logger = logging.getLogger("worker")


async def send_telegram_notification(ctx, lead_id: int, lead_dict: dict) -> None:
    success = await deliver_and_record(lead_id, lead_dict)
    if success:
        return

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        attempts = lead.telegram_attempts if lead else settings.telegram_max_attempts
    finally:
        db.close()

    if attempts >= settings.telegram_max_attempts:
        logger.warning("lead_id=%s исчерпал лимит попыток Telegram (%s из %s)", lead_id, attempts, settings.telegram_max_attempts)
        return

    backoff = settings.telegram_retry_backoff_seconds * (2 ** (attempts - 1))
    logger.info("lead_id=%s: попытка %s не удалась, повтор через %sс", lead_id, attempts, backoff)
    await ctx["redis"].enqueue_job("send_telegram_notification", lead_id, lead_dict, _defer_by=backoff)


async def retry_failed_telegram_notifications(ctx) -> None:
    """
    Каждые 15 минут (см. cron_jobs) подхватывает заявки с
    telegram_status='failed', у которых остались попытки и прошло не
    меньше backoff-интервала с последней — подстраховка на случай, если
    отложенная через _defer_by задача не выполнилась (перезапуск воркера,
    падение Redis между постановкой и исполнением и т.п.).
    """
    db = SessionLocal()
    try:
        candidates = db.query(Lead).filter(Lead.telegram_status == "failed").all()
        now = datetime.now(timezone.utc)
        requeued = 0
        for lead in candidates:
            if lead.telegram_attempts >= settings.telegram_max_attempts:
                continue
            backoff = settings.telegram_retry_backoff_seconds * (2 ** max(lead.telegram_attempts - 1, 0))
            last_attempt = lead.telegram_last_attempt_at
            if last_attempt is not None:
                last_attempt_aware = last_attempt.replace(tzinfo=timezone.utc)
                if now - last_attempt_aware < timedelta(seconds=backoff):
                    continue
            await ctx["redis"].enqueue_job("send_telegram_notification", lead.id, lead_to_notification_dict(lead))
            requeued += 1
        if requeued:
            logger.info("Sweep: повторно поставлено в очередь %s заявок", requeued)
    finally:
        db.close()


class WorkerSettings:
    functions = [send_telegram_notification]
    cron_jobs = [cron(retry_failed_telegram_notifications, minute=set(range(0, 60, 15)))]
    redis_settings = RedisSettings.from_dsn(settings.redis_url) if settings.redis_url else RedisSettings()
