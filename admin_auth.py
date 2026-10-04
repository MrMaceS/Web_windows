"""
admin_auth.py
Сессионная аутентификация админки (cookie, подписанный itsdangerous через
Starlette SessionMiddleware — подключается в main.py) + простой RBAC
на двух ролях: "admin" (полный доступ) и "manager" (только заявки).
"""

from typing import Optional
import secrets

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database import get_db, AdminUser


class AdminAuthRequired(Exception):
    """Нет валидной сессии администратора — нужно на /admin/login."""


class AdminForbidden(Exception):
    """Есть сессия, но роль не подходит для этого действия."""


def get_current_admin_optional(request: Request, db: Session = Depends(get_db)) -> Optional[AdminUser]:
    admin_id = request.session.get("admin_user_id")
    if not admin_id:
        return None
    admin = db.query(AdminUser).filter(AdminUser.id == admin_id, AdminUser.is_active.is_(True)).first()
    if admin is None:
        request.session.clear()
    return admin


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    admin = get_current_admin_optional(request, db)
    if admin is None:
        raise AdminAuthRequired()
    return admin


def require_role(*roles: str):
    """Фабрика зависимостей: Depends(require_role("admin")) или
    Depends(require_role("admin", "manager")) для роутов, доступных обеим ролям."""

    def dependency(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if admin.role not in roles:
            raise AdminForbidden()
        return admin

    return dependency


class CsrfError(Exception):
    """Токен CSRF в форме отсутствует или не совпадает с токеном сессии."""


def get_or_create_csrf_token(request: Request) -> str:
    """Токен генерируется один раз за сессию (при логине) и переиспользуется
    во всех формах админки — обычная защита от подделки межсайтовых
    запросов для админки на cookie-сессиях."""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verify_csrf(request: Request, csrf_token: str) -> None:
    expected = request.session.get("csrf_token")
    if not expected or not secrets.compare_digest(csrf_token, expected):
        raise CsrfError()
