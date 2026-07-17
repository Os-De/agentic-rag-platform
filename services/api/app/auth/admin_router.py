"""Admin endpoints (Phase 4): user management + audit trail access."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_role
from app.auth.schemas import AuditLogOut, UserOut, UserUpdate
from app.core.audit import audit
from app.db.models import AuditLog, User
from app.db.session import get_db

log = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)).all())


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> User:
    """Change a user's role and/or disable the account (soft delete keeps the trail)."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    demoting_self = target.id == admin.id and (
        payload.is_active is False or (payload.role is not None and payload.role != "admin")
    )
    if demoting_self:  # never lock the last key inside the car
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="You cannot demote or disable your own account"
        )

    changes = []
    if payload.role is not None and payload.role != target.role:
        changes.append(f"role:{target.role}->{payload.role}")
        target.role = payload.role
    if payload.is_active is not None and payload.is_active != target.is_active:
        changes.append(f"is_active:{target.is_active}->{payload.is_active}")
        target.is_active = payload.is_active

    if changes:
        db.commit()
        db.refresh(target)
        audit(db, actor=admin.email, action="user.update", resource=target.email,
              detail="; ".join(changes))
        log.info("user updated", target=target.email, by=admin.email, changes=changes)
    return target


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit_log(
    limit: int = 100,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    """Most recent privileged actions, newest first."""
    limit = max(1, min(limit, 1000))
    return list(
        db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        ).all()
    )
