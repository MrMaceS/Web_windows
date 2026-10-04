"""
tests/test_frontend_layout.py
Браузерные регрессионные тесты вёрстки — страхуют баги, найденные при интеграции Stitch:
  * закрытый <dialog> мобильного меню рисовался поверх страницы
    (author-стиль display:flex перебивал UA-правило dialog:not([open]){display:none});
  * горизонтальный скролл на узких экранах (privacy/404 — 320 px, каталог — 768 px);
  * открытое мобильное меню оставалось «живым» после растягивания окна до desktop.

Тесты необязательные: нужны playwright + Chromium (`pip install playwright && playwright install chromium`)
и собранный CSS (`npm run build:css`). Без них — skip, обычный pytest не ломается.
"""

import socket
import threading
import time
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api", reason="playwright не установлен")

ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "static" / "css" / "output.css").exists():
    pytest.skip("нет static/css/output.css — выполните npm run build:css", allow_module_level=True)

PAGES = ["/", "/privacy", "/nope-404/", "/okna/", "/okna/dvuhstvorchatye/"]
WIDTHS = [320, 375, 768, 1280]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live_url(client):
    """Реальный HTTP-сервер поверх приложения с подменённой тестовой БД (см. conftest.client)."""
    import uvicorn
    import main

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        pytest.fail("тестовый сервер не стартовал")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def browser():
    with playwright_sync.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # браузер не установлен
            pytest.skip(f"Chromium недоступен: {exc}")
        yield b
        b.close()


def test_closed_dialogs_are_not_rendered(live_url, browser):
    page = browser.new_context(viewport={"width": 375, "height": 800}).new_page()
    page.goto(live_url + "/")
    displays = page.evaluate(
        "[...document.querySelectorAll('dialog:not([open])')].map(d => [d.id, getComputedStyle(d).display])"
    )
    assert displays, "на странице должны быть диалоги (меню и модалки)"
    visible = [d for d in displays if d[1] != "none"]
    assert not visible, f"закрытые диалоги участвуют в вёрстке: {visible}"


@pytest.mark.parametrize("width", WIDTHS)
def test_no_horizontal_scroll(live_url, browser, width):
    page = browser.new_context(viewport={"width": width, "height": 800}).new_page()
    for path in PAGES:
        page.goto(live_url + path)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"{path} @ {width}px: горизонтальный скролл +{overflow}px"


def test_mobile_menu_closes_when_viewport_becomes_desktop(live_url, browser):
    page = browser.new_context(viewport={"width": 800, "height": 800}).new_page()
    page.goto(live_url + "/")
    page.locator('[data-open-dialog="mobile-menu"]').click()
    assert page.evaluate("document.getElementById('mobile-menu').open")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_function("!document.getElementById('mobile-menu').open", timeout=3000)
    # событие close (оно снимает блокировку прокрутки) приходит асинхронно — ждём состояние, а не момент
    page.wait_for_function("!document.documentElement.classList.contains('is-scroll-locked')", timeout=3000)
