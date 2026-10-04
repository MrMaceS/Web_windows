import json
import logging

import httpx
import pytest

import bot


@pytest.fixture()
def telegram_configured(monkeypatch):
    monkeypatch.setattr(bot.settings, "telegram_bot_token", "123456:SECRET-TOKEN")
    monkeypatch.setattr(bot.settings, "telegram_chat_id", "-1001")


def _patch_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(bot.httpx, "AsyncClient", factory)


def test_message_contains_calculator_data_and_utm():
    text = bot._format_lead_message({
        "source": "calculator", "name": "Иван", "phone": "+79001234567",
        "window_type": "Окно", "profile_type": "Стандарт (70 мм)",
        "width_mm": 1300, "height_mm": 1400, "quantity": 2, "calculated_price": 19105.4,
        "utm_source": "yandex", "utm_campaign": "windows",
    })
    assert "+79001234567" in text
    assert "1300×1400" in text
    assert "19105" in text
    assert "source=yandex" in text and "campaign=windows" in text


def test_user_input_is_html_escaped():
    text = bot._format_lead_message({"source": "hero_form", "name": "<b>Хакер", "phone": "+79001234567", "comment": "<script>"})
    assert "<b>Хакер" not in text
    assert "&lt;b&gt;Хакер" in text
    assert "&lt;script&gt;" in text


@pytest.mark.asyncio
async def test_send_returns_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(bot.settings, "telegram_bot_token", "")
    assert await bot.send_lead_to_telegram({"phone": "+79001234567"}) is False


@pytest.mark.asyncio
async def test_send_success(monkeypatch, telegram_configured):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    _patch_transport(monkeypatch, handler)
    assert await bot.send_lead_to_telegram({"phone": "+79001234567"}) is True
    assert captured["url"].endswith("/bot123456:SECRET-TOKEN/sendMessage")
    assert captured["body"]["chat_id"] == "-1001"
    assert captured["body"]["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_send_failure_returns_false_and_does_not_log_token(monkeypatch, telegram_configured, caplog):
    _patch_transport(monkeypatch, lambda request: httpx.Response(400, json={"ok": False}))
    with caplog.at_level(logging.ERROR, logger="bot"):
        assert await bot.send_lead_to_telegram({"phone": "+79001234567"}) is False
    assert "SECRET-TOKEN" not in caplog.text
    assert "400" in caplog.text


@pytest.mark.asyncio
async def test_send_network_error_returns_false(monkeypatch, telegram_configured, caplog):
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)
    with caplog.at_level(logging.ERROR, logger="bot"):
        assert await bot.send_lead_to_telegram({"phone": "+79001234567"}) is False
    assert "SECRET-TOKEN" not in caplog.text
