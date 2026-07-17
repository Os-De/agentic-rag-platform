"""AuthN/AuthZ dependencies — hierarchical RBAC (see ADR-005, architecture §6).

Usage in routers:
    user = Depends(get_current_user)          # any authenticated user
    user = Depends(require_role("engineer"))  # engineer or admin
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# Hierarchy: a higher rank includes all permissions below it.
ROLE_RANK: dict[str, int] = {"viewer": 0, "engineer": 1, "admin": 2}


def has_permission(user_role: str, min_role: str) -> bool:
    """Pure RBAC check — unit-testable without FastAPI."""
    return ROLE_RANK.get(user_role, -1) >= ROLE_RANK[min_role]


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise unauthorized from None

    email = payload.get("sub")
    if not email:
        raise unauthorized
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise unauthorized
    if not user.is_active:  # Phase 4: soft-disabled accounts keep their rows + audit trail
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return user


def require_role(min_role: str):
    """Dependency factory: allow only users with `min_role` or higher."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{min_role}' or higher (you are '{user.role}')",
            )
        return user

    return checker
