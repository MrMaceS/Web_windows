"""
tests/test_assets.py
Версионирование статики: nginx отдаёт /static/ с immutable на 30 дней, поэтому каждый CSS/JS
в шаблонах обязан подключаться через asset() — иначе после деплоя пользователи получат старые файлы.
"""

import re
from pathlib import Path

import pytest

import assets

ROOT = Path(__file__).resolve().parent.parent


def test_asset_adds_content_hash():
    url = assets.asset("css/output.css")
    assert re.fullmatch(r"/static/css/output\.css\?v=[0-9a-f]{10}", url), url


def test_asset_accepts_leading_slash_and_static_prefix():
    expected = assets.asset("js/main.js")
    assert assets.asset("/js/main.js") == expected
    assert assets.asset("/static/js/main.js") == expected


def test_asset_version_is_stable_and_changes_with_content(tmp_path, monkeypatch):
    (tmp_path / "a.js").write_text("one", encoding="utf-8")
    monkeypatch.setattr(assets, "STATIC_DIR", tmp_path.resolve())
    monkeypatch.setattr(assets, "_cache", {})

    first = assets.asset("a.js")
    assert assets.asset("a.js") == first, "версия должна быть стабильной между вызовами"

    f = tmp_path / "a.js"
    f.write_text("two", encoding="utf-8")
    # mtime мог не измениться при быстрой перезаписи — сдвигаем явно, как это сделал бы деплой
    st = f.stat()
    import os

    os.utime(f, (st.st_atime, st.st_mtime + 5))
    assert assets.asset("a.js") != first, "после изменения файла URL обязан измениться"


@pytest.mark.parametrize("bad", ["../main.py", "../../etc/passwd", "css/../../main.py", "/static/../config.py"])
def test_asset_does_not_escape_static_dir(bad):
    url = assets.asset(bad)
    assert "?v=" not in url, f"{bad}: файл вне static/ не должен получать версию (и читаться)"


def test_asset_missing_file_returns_plain_url_not_error():
    assert assets.asset("js/no-such-file.js") == "/static/js/no-such-file.js"


def test_pages_use_versioned_assets(client):
    for path in ("/", "/privacy"):
        html = client.get(path, headers={"accept": "text/html"}).text
        links = re.findall(r'(?:href|src)="(/static/(?:css|js)/[^"]+)"', html)
        assert links, f"{path}: не найдено ссылок на CSS/JS"
        unversioned = [u for u in links if "?v=" not in u]
        assert not unversioned, f"{path}: статика без версии (кэш immutable 30 дней): {unversioned}"


def test_no_hardcoded_css_js_links_in_templates():
    """Любая новая прямая ссылка /static/css|js/... в шаблоне должна идти через asset()."""
    offenders = []
    for tpl in (ROOT / "templates").rglob("*.html"):
        for n, line in enumerate(tpl.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'(?:href|src)="/static/(?:css|js)/', line):
                offenders.append(f"{tpl.relative_to(ROOT)}:{n}")
    assert not offenders, f"прямые ссылки на статику без asset(): {offenders}"
