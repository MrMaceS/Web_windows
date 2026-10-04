"""
tests/test_deploy_config.py
Конфигурация деплоя, от которой зависит корректность rate limit (slowapi считает лимит по IP).

Эксперимент показал три режима:
  * Nginx не в FORWARDED_ALLOW_IPS  -> все посетители «один адрес», 1 человек блокирует форму и вход в админку всем;
  * FORWARDED_ALLOW_IPS=* + Nginx ДОПИСЫВАЕТ X-Forwarded-For -> лимит обходится подделкой заголовка;
  * FORWARDED_ALLOW_IPS=* + Nginx ПЕРЕЗАПИСЫВАЕТ заголовок + app не опубликован -> верно.
Эти тесты не дают незаметно откатиться в один из плохих режимов.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NGINX = (ROOT / "nginx" / "nginx.conf").read_text(encoding="utf-8")


def test_nginx_overwrites_x_forwarded_for():
    assert re.search(r"proxy_set_header\s+X-Forwarded-For\s+\$remote_addr\s*;", NGINX), (
        "X-Forwarded-For должен перезаписываться $remote_addr"
    )
    # проверяем только директивы, а не комментарии, где переменная упоминается в пояснении
    directives = "\n".join(line for line in NGINX.splitlines() if not line.lstrip().startswith("#"))
    assert "$proxy_add_x_forwarded_for" not in directives, (
        "дописывание клиентского X-Forwarded-For позволяет подделать IP и обойти rate limit"
    )


def test_dockerfile_runs_uvicorn_with_proxy_headers():
    cmd = next(line for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines() if line.startswith("CMD"))
    assert "uvicorn" in cmd and "--proxy-headers" in cmd


def _compose():
    yaml = pytest.importorskip("yaml", reason="PyYAML не установлен")
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_app_sees_real_client_ip():
    services = _compose()["services"]
    for name in ("app", "worker", "migrate"):
        env = services[name]["environment"]
        assert "DATABASE_URL" in env, f"{name}: DATABASE_URL потерян (merge якоря x-app)"
        assert "FORWARDED_ALLOW_IPS" in env, f"{name}: нет FORWARDED_ALLOW_IPS"


def test_compose_app_is_not_published():
    """FORWARDED_ALLOW_IPS=* безопасен только пока до app нельзя достучаться в обход nginx."""
    services = _compose()["services"]
    for name in ("app", "db", "redis"):
        assert "ports" not in services[name], f"сервис {name} не должен публиковать порты наружу"
    assert services["nginx"]["ports"], "наружу должен смотреть nginx"


# ---------- HTTPS-вариант (nginx/nginx.https.conf.example) ----------
HTTPS = (ROOT / "nginx" / "nginx.https.conf.example").read_text(encoding="utf-8")


def _csp_map(text: str) -> str:
    m = re.search(r"map \$uri \$csp_policy \{.*?\n\}", text, re.S)
    assert m, "в конфиге не найден map с CSP"
    return m.group(0)


def test_https_config_has_same_csp_as_http_config():
    assert _csp_map(HTTPS) == _csp_map(NGINX), "CSP в nginx.https.conf.example разошёлся с nginx.conf"


def test_https_config_keeps_proxy_and_header_settings():
    directives = "\n".join(line for line in HTTPS.splitlines() if not line.lstrip().startswith("#"))
    assert re.search(r"proxy_set_header\s+X-Forwarded-For\s+\$remote_addr\s*;", directives)
    assert "$proxy_add_x_forwarded_for" not in directives
    for needle in ("proxy_hide_header X-Frame-Options", "Content-Security-Policy $csp_policy", "X-Content-Type-Options"):
        assert needle in directives, f"в HTTPS-конфиге пропало: {needle}"


def test_https_config_tls_and_redirect():
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in HTTPS
    assert "Strict-Transport-Security" in HTTPS
    assert re.search(r"listen 80;.*?/.well-known/acme-challenge/.*?return 301 https://", HTTPS, re.S)
    assert "listen 443 ssl;" in HTTPS


def test_compose_tls_override_publishes_443():
    yaml = pytest.importorskip("yaml", reason="PyYAML не установлен")
    data = yaml.safe_load((ROOT / "docker-compose.tls.yml").read_text(encoding="utf-8"))
    assert "443:443" in data["services"]["nginx"]["ports"]
