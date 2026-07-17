import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_role
from app.auth.schemas import PasswordChange, Token, UserCreate, UserOut
from app.core.audit import audit
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
@limiter.limit(get_settings().rate_limit_login)  # Phase 4: brute-force protection
def login(
    request: Request,  # required by slowapi
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """OAuth2 password flow. `username` field carries the email."""
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.hashed_password):
        # Same error for unknown user / wrong password — no user enumeration.
        audit(db, actor=form.username, action="login.failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        audit(db, actor=user.email, action="login.disabled_account")
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account disabled")
    log.info("login", user=user.email, role=user.role)
    audit(db, actor=user.email, action="login.success")
    return Token(access_token=create_access_token(subject=user.email, role=user.role))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
) -> User:
    """Admin-only user creation (first admin is seeded from env at startup)."""
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("user registered", user=user.email, role=user.role, by=admin.email)
    audit(db, actor=admin.email, action="user.register", resource=user.email,
          detail=f"role={user.role}")
    return user


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Self-service password change (any authenticated user)."""
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Current password incorrect")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    audit(db, actor=user.email, action="user.change_password")
    log.info("password changed", user=user.email)
