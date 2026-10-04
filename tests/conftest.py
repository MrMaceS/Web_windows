"""
tests/conftest.py
Тесты используют изолированную SQLite-БД в памяти вместо реального Postgres —
приложение полностью БД-агностично через SQLAlchemy, поэтому это честная
проверка бизнес-логики (валидация, honeypot, rate-limit) без поднятия
инфраструктуры. Postgres-специфичные вещи (типы данных, миграции Alembic)
тестами здесь не покрываются — для этого в CI стоит поднимать реальный
Postgres через docker-compose и гонять эти же тесты против него.
"""

import os
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_startup_fallback.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
import main
from rate_limit import limiter


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    database.Base.metadata.create_all(bind=engine)

    seed_db = TestingSessionLocal()
    try:
        database.seed_default_price_rules(seed_db)
        database.seed_catalog_if_empty(seed_db)
    finally:
        seed_db.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[database.get_db] = override_get_db

    monkeypatch.setattr("telegram_delivery.SessionLocal", TestingSessionLocal)

    limiter.reset()

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(client):
    """Создаёт тестового администратора (role=admin) прямо в тестовой БД,
    через тот же override_get_db, что использует client — гарантирует,
    что это ОДНА и та же база, а не глобальная."""
    from security import hash_password
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        user = database.AdminUser(
            username="test-admin", password_hash=hash_password("test-password-123"), role="admin", is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture()
def manager_user(client):
    from security import hash_password
    import database
    import main

    db_gen = main.app.dependency_overrides[database.get_db]()
    db = next(db_gen)
    try:
        user = database.AdminUser(
            username="test-manager", password_hash=hash_password("test-password-123"), role="manager", is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, "CSRF-токен не найден на странице — проверьте base_admin.html"
    return match.group(1)


def _wrap_post_with_csrf(test_client, token: str):
    """
    Тесты в test_admin.py пишут admin_client.post("/admin/...", data={...})
    без csrf_token — переписывать десятки вызовов непрактично. Вместо этого
    подставляем токен автоматически для всех запросов на /admin/*, если он
    ещё не передан явно. Токен один на всю сессию (см. get_or_create_csrf_token),
    поэтому достаточно получить его один раз сразу после логина.
    """
    original_post = test_client.post

    def post_with_csrf(url, data=None, **kwargs):
        if url.startswith("/admin/") and kwargs.get("json") is None:
            data = {**(data or {}), "csrf_token": token} if "csrf_token" not in (data or {}) else data
        return original_post(url, data=data, **kwargs)

    test_client.post = post_with_csrf


@pytest.fixture()
def admin_client(client, admin_user):
    """TestClient с уже выполненным логином под администратором —
    сессионная cookie сохраняется в самом TestClient между запросами."""
    response = client.post("/admin/login", data={"username": "test-admin", "password": "test-password-123"})
    assert response.status_code in (200, 303)
    token = _extract_csrf_token(client.get("/admin/").text)
    _wrap_post_with_csrf(client, token)
    return client


@pytest.fixture()
def manager_client(client, manager_user):
    response = client.post("/admin/login", data={"username": "test-manager", "password": "test-password-123"})
    assert response.status_code in (200, 303)
    token = _extract_csrf_token(client.get("/admin/").text)
    _wrap_post_with_csrf(client, token)
    return client
