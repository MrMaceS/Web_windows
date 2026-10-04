"""
audit.py
Запись действий администраторов в audit_log.
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from database import AdminUser, AuditLog


def record_audit(
    db: Session,
    admin: AdminUser,
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> None:
    entry = AuditLog(
        admin_user_id=admin.id,
        admin_username=admin.username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
        after_json=json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
    )
    db.add(entry)
