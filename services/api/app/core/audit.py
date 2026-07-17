"""Audit trail (Phase 4): who did what, when — for every privileged action.

Best-effort by design: an audit failure must never break the user's request,
but it is always logged.
"""

import structlog
from sqlalchemy.orm import Session

from app.db.models import AuditLog

log = structlog.get_logger()


def audit(db: Session, actor: str, action: str, resource: str = "", detail: str = "") -> None:
    try:
        db.add(AuditLog(actor=actor, action=action, resource=resource, detail=detail[:2000]))
        db.commit()
    except Exception as exc:
        db.rollback()
        log.warning("audit write failed", action=action, error=str(exc))
