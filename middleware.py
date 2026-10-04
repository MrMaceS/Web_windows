"""
middleware.py
- RequestIdMiddleware: генерирует/пробрасывает X-Request-ID, кладёт его
  в contextvar для structured-логов (logging_config.py) и возвращает
  клиенту в заголовке ответа — удобно для саппорта ("дайте request id").
- SecurityHeadersMiddleware: базовый набор security-заголовков.
  Полноценный Content-Security-Policy лучше настраивать на уровне Nginx
  (см. nginx/nginx.conf), здесь — заголовки, которые не конфликтуют
  с инлайновыми <script>/<style>, уже используемыми в шаблонах.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from logging_config import request_id_var

logger = logging.getLogger("http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming_id = request.headers.get("X-Request-ID")
        req_id = incoming_id or str(uuid.uuid4())
        token = request_id_var.set(req_id)

        start = time.monotonic()
        status = "ERR"
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info("%s %s -> %s (%sms)", request.method, request.url.path, status, duration_ms)
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response
