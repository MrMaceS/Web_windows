"""
tests/test_csp_and_head.py
Страхуют две вещи, доработанные при интеграции фронтенда:

1. Совместимость со строгим CSP из nginx/nginx.conf: на публичных страницах и в админке
   не должно быть inline-скриптов и inline-обработчиков (onclick=, onchange=, ...).
   Если кто-то вернёт <script>...</script> или onchange="...", CSP заблокирует их в проде,
   а локально (без nginx) этого не видно — тест ловит такое заранее.
2. HEAD-запросы к публичным маршрутам отвечают так же, как GET (раньше было 405):
   на это опираются мониторинг доступности и часть краулеров.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_PAGES = ["/", "/privacy", "/does-not-exist/", "/okna/", "/okna/dvuhstvorchatye/"]

# исполняемый inline-<script>: без src и не JSON-LD (тип application/ld+json браузер не исполняет)
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>", re.I)
INLINE_HANDLER = re.compile(r"""<[a-z][^>]*\son[a-z]+\s*=""", re.I)
INLINE_STYLE_ATTR = re.compile(r"""<[a-z][^>]*\sstyle\s*=""", re.I)


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_are_csp_clean(client, path):
    # Accept как у браузера: без него страница 404 отдаётся JSON-ом, и проверять было бы нечего
    resp = client.get(path, headers={"accept": "text/html"})
    assert "text/html" in resp.headers["content-type"], f"{path}: ожидался HTML, получен {resp.headers['content-type']}"
    html = resp.text
    assert not INLINE_SCRIPT.search(html), f"{path}: inline-скрипт заблокируется CSP (script-src 'self')"
    assert not INLINE_HANDLER.search(html), f"{path}: inline-обработчик события заблокируется CSP"
    assert not INLINE_STYLE_ATTR.search(html), f"{path}: style=\"...\" заблокируется CSP (style-src 'self')"


def test_admin_templates_have_no_inline_scripts_or_handlers():
    """Админка получает style-src 'unsafe-inline' (график), но скрипты и обработчики — строго запрещены."""
    for tpl in (ROOT / "templates" / "admin").glob("*.html"):
        src = tpl.read_text(encoding="utf-8")
        assert not INLINE_SCRIPT.search(src), f"{tpl.name}: inline-скрипт"
        assert not INLINE_HANDLER.search(src), f"{tpl.name}: inline-обработчик события"


def test_ym_counter_id_is_passed_via_data_attribute(client, monkeypatch):
    import config

    monkeypatch.setattr(config.settings, "yandex_metrika_id", "12345678")
    html = client.get("/privacy").text
    assert 'data-ym-id="12345678"' in html
    assert "APP_CONFIG" not in html


@pytest.mark.parametrize("path", ["/", "/privacy", "/okna/", "/robots.txt", "/sitemap.xml", "/health"])
def test_head_matches_get(client, path):
    get = client.get(path)
    head = client.head(path)
    assert head.status_code == get.status_code == 200, f"{path}: HEAD={head.status_code}, GET={get.status_code}"
    assert head.content == b""
    assert head.headers["content-type"] == get.headers["content-type"]


def test_head_on_missing_page_is_404(client):
    assert client.head("/does-not-exist/").status_code == 404


def test_nginx_csp_is_strict_for_public_site():
    conf = (ROOT / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "Content-Security-Policy $csp_policy" in conf
    m = re.search(r'default\s+"([^"]+)";', conf)
    assert m, "в map не найдена публичная политика (default)"
    public = m.group(1)
    assert "default-src 'self'" in public
    assert "object-src 'none'" in public and "frame-ancestors 'none'" in public
    assert "'unsafe-inline'" not in public and "'unsafe-eval'" not in public
    # единственный внешний хост — Яндекс.Метрика
    hosts = set(re.findall(r"https://([a-z0-9.-]+)", public))
    assert hosts <= {"mc.yandex.ru", "yastatic.net"}, f"неожиданные внешние хосты в CSP: {hosts}"
