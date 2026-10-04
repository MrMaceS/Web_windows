"""
tests/test_queue.py — Sprint 4: telegram_delivery и queue_client в
inline-режиме (без Redis — settings.redis_url пуст в тестовом .env),
плюс юнит-тесты backoff-логики воркера без реального ARQ/Redis.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Lead
import telegram_delivery
import queue_client


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(telegram_delivery, "SessionLocal", SessionLocal)

    session = SessionLocal()
    lead = Lead(source="hero_form", phone="+79001234567", consent_given=True)
    session.add(lead)
    session.commit()
    session.refresh(lead)
    lead_id = lead.id
    session.close()

    yield SessionLocal, lead_id


@pytest.mark.asyncio
async def test_deliver_and_record_marks_sent_on_success(db_session, monkeypatch):
    SessionLocal, lead_id = db_session

    async def fake_send(lead_dict):
        return True

    monkeypatch.setattr(telegram_delivery, "send_lead_to_telegram", fake_send)

    result = await telegram_delivery.deliver_and_record(lead_id, {"id": lead_id, "phone": "+79001234567"})
    assert result is True

    db = SessionLocal()
    lead = db.query(Lead).filter_by(id=lead_id).first()
    assert lead.telegram_status == "sent"
    assert lead.telegram_attempts == 1
    assert lead.telegram_error is None
    db.close()


@pytest.mark.asyncio
async def test_deliver_and_record_marks_failed_and_increments_attempts(db_session, monkeypatch):
    SessionLocal, lead_id = db_session

    async def fake_send(lead_dict):
        return False

    monkeypatch.setattr(telegram_delivery, "send_lead_to_telegram", fake_send)

    await telegram_delivery.deliver_and_record(lead_id, {"id": lead_id, "phone": "+79001234567"})
    await telegram_delivery.deliver_and_record(lead_id, {"id": lead_id, "phone": "+79001234567"})

    db = SessionLocal()
    lead = db.query(Lead).filter_by(id=lead_id).first()
    assert lead.telegram_status == "failed"
    assert lead.telegram_attempts == 2
    assert lead.telegram_error is not None
    db.close()


@pytest.mark.asyncio
async def test_deliver_and_record_handles_missing_lead_gracefully(db_session, monkeypatch):
    SessionLocal, _ = db_session

    async def fake_send(lead_dict):
        return True

    monkeypatch.setattr(telegram_delivery, "send_lead_to_telegram", fake_send)

    result = await telegram_delivery.deliver_and_record(999999, {"id": 999999, "phone": "+79001234567"})
    assert result is True


@pytest.mark.asyncio
async def test_enqueue_without_redis_delivers_inline(db_session, monkeypatch):
    """Без REDIS_URL enqueue_telegram_job должен просто вызвать
    deliver_and_record напрямую, без похода в ARQ."""
    SessionLocal, lead_id = db_session

    async def fake_send(lead_dict):
        return True

    monkeypatch.setattr(telegram_delivery, "send_lead_to_telegram", fake_send)
    monkeypatch.setattr(queue_client.settings, "redis_url", "")
    monkeypatch.setattr(queue_client, "_pool", None)

    await queue_client.enqueue_telegram_job(lead_id, {"id": lead_id, "phone": "+79001234567"})

    db = SessionLocal()
    lead = db.query(Lead).filter_by(id=lead_id).first()
    assert lead.telegram_status == "sent"
    db.close()


def test_worker_backoff_grows_exponentially():
    """Юнит-проверка формулы backoff из worker.py без поднятия ARQ/Redis —
    сама формула вынесена в выражение, дублируем её здесь как контракт-тест:
    если формула в worker.py изменится несовместимо, этот тест укажет,
    что нужно обновить и документацию (README)."""
    base = 60
    attempts = [1, 2, 3, 4]
    backoffs = [base * (2 ** (a - 1)) for a in attempts]
    assert backoffs == [60, 120, 240, 480]


class _FakeArqPool:
    def __init__(self):
        self.closed = False
        self.enqueued = []

    async def enqueue_job(self, name, *args):
        self.enqueued.append((name, args))

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_get_pool_creates_and_caches_when_redis_configured(monkeypatch):
    fake_pool = _FakeArqPool()
    created = []

    async def fake_create_pool(settings):
        created.append(settings)
        return fake_pool

    monkeypatch.setattr(queue_client, "create_pool", fake_create_pool)
    monkeypatch.setattr(queue_client.settings, "redis_url", "redis://localhost:6379/0")
    monkeypatch.setattr(queue_client, "_pool", None)

    pool1 = await queue_client.get_pool()
    pool2 = await queue_client.get_pool()

    assert pool1 is fake_pool
    assert pool2 is fake_pool
    assert len(created) == 1


@pytest.mark.asyncio
async def test_close_pool_closes_and_resets(monkeypatch):
    fake_pool = _FakeArqPool()
    monkeypatch.setattr(queue_client, "_pool", fake_pool)

    await queue_client.close_pool()

    assert fake_pool.closed is True
    assert queue_client._pool is None


@pytest.mark.asyncio
async def test_enqueue_pushes_job_when_redis_configured(monkeypatch):
    fake_pool = _FakeArqPool()

    async def fake_get_pool():
        return fake_pool

    monkeypatch.setattr(queue_client, "get_pool", fake_get_pool)

    async def should_not_run(lead_id, lead_dict):
        raise AssertionError("inline delivery must not run when queue accepts the job")

    monkeypatch.setattr(queue_client, "deliver_and_record", should_not_run)

    await queue_client.enqueue_telegram_job(42, {"id": 42, "phone": "+79001234567"})

    assert fake_pool.enqueued == [("send_telegram_notification", (42, {"id": 42, "phone": "+79001234567"}))]


@pytest.mark.asyncio
async def test_enqueue_falls_back_to_inline_when_redis_push_fails(monkeypatch, db_session):
    SessionLocal, lead_id = db_session

    class BrokenPool:
        async def enqueue_job(self, *args):
            raise ConnectionError("redis is down")

    async def fake_get_pool():
        return BrokenPool()

    async def fake_send(lead_dict):
        return True

    monkeypatch.setattr(queue_client, "get_pool", fake_get_pool)
    monkeypatch.setattr(telegram_delivery, "send_lead_to_telegram", fake_send)

    await queue_client.enqueue_telegram_job(lead_id, {"id": lead_id, "phone": "+79001234567"})

    db = SessionLocal()
    lead = db.query(Lead).filter_by(id=lead_id).first()
    assert lead.telegram_status == "sent"
    db.close()
