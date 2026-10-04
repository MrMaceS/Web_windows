"""
tests/test_requirements.py
Нижние границы версий, ниже которых проект не ставится на Windows с новым Python.

История: закреплённый psycopg2-binary==2.9.9 не имеет готовой сборки (wheel) под Python 3.13+,
и pip пытался компилировать его из исходников — на Windows это падало с «pg_config executable not found».
Аналогично pydantic < 2.12 (pydantic-core) не имеет сборок под Python 3.14.
Поэтому понижать эти версии нельзя, пока проект заявляет поддержку Python 3.12–3.14.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pinned(name: str) -> tuple[int, ...]:
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^{re.escape(name)}==([\d.]+)", line.strip(), re.I)
        if m:
            return tuple(int(x) for x in m.group(1).split("."))
    raise AssertionError(f"{name} не закреплён в requirements.txt")


def test_psycopg2_binary_has_wheels_for_python_3_14():
    assert _pinned("psycopg2-binary") >= (2, 9, 11)


def test_pydantic_has_wheels_for_python_3_14():
    assert _pinned("pydantic") >= (2, 12, 0)
    assert _pinned("pydantic-settings") >= (2, 12, 0)
