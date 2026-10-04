"""
queue_client.py
Единая точка постановки задачи отправки Telegram-уведомления.
"""

import logging
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from config import settings
from telegram_delivery import deliver_and_record

logger = logging.getLogger("queue_client")

_pool: Optional[ArqRedis] = None


async def get_pool() -> Optional[ArqRedis]:
    global _pool
    if not settings.redis_url:
        return None
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def enqueue_telegram_job(lead_id: int, lead_dict: dict) -> None:
    pool = await get_pool()
    if pool is None:
        await deliver_and_record(lead_id, lead_dict)
        return

    try:
        await pool.enqueue_job("send_telegram_notification", lead_id, lead_dict)
    except Exception:
        logger.exception("Не удалось поставить задачу в ARQ, отправляю напрямую")
        await deliver_and_record(lead_id, lead_dict)
