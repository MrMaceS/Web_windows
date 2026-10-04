"""
assets.py — версионирование статики (cache busting).

Nginx отдаёт /static/ с `Cache-Control: immutable` на 30 дней, а имена файлов без хеша.
Без версии в URL браузеры после деплоя продолжали бы использовать старые CSS/JS.
asset("css/output.css") -> "/static/css/output.css?v=<10 символов sha1 содержимого>":
URL меняется только когда меняется файл, поэтому долгий кэш безопасен.
"""

import hashlib
from pathlib import Path

STATIC_DIR = (Path(__file__).resolve().parent / "static").resolve()

# rel-путь -> (mtime, версия): файл перечитывается, только если изменился
_cache: dict[str, tuple[float, str]] = {}


def asset(path: str) -> str:
    rel = path.lstrip("/")
    if rel.startswith("static/"):
        rel = rel[len("static/") :]
    base = f"/static/{rel}"

    full = (STATIC_DIR / rel).resolve()
    # защита от ../ и симлинков наружу; несуществующий файл — без версии, а не 500
    if STATIC_DIR not in full.parents or not full.is_file():
        return base

    mtime = full.stat().st_mtime
    cached = _cache.get(rel)
    if cached is None or cached[0] != mtime:
        cached = (mtime, hashlib.sha1(full.read_bytes()).hexdigest()[:10])
        _cache[rel] = cached
    return f"{base}?v={cached[1]}"
