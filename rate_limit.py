"""
rate_limit.py
Rate limiting по IP через slowapi (обёртка над limits).
Защищает формы от простого автоматизированного спама/перебора —
не замена полноценной WAF/капчи, но обязательный базовый уровень.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
