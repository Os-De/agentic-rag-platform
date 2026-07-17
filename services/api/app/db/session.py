"""Engine, session dependency, and first-run initialization (tables + admin seed)."""

from collections.abc import Generator

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base, Role, User

log = structlog.get_logger()

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _lightweight_migrations() -> None:
    """Stopgap until Alembic (Phase 4 extension): idempotent, additive-only ALTERs.

    create_all creates missing TABLES but never alters existing ones — so columns
    added after a database was first created must be patched in here.
    """
    if engine.dialect.name != "postgresql":  # sqlite (tests) lacks IF NOT EXISTS
        return
    from sqlalchemy import text

    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def init_db() -> None:
    """Create tables and seed the first admin from env (bootstrap — see ADR-005).

    Phase 4 upgrade path: replace create_all + _lightweight_migrations with Alembic.
    """
    from app.core.security import hash_password  # local import avoids cycle

    Base.metadata.create_all(bind=engine)
    _lightweight_migrations()
    settings = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)) is None:
            db.add(
                User(
                    email=settings.admin_email,
                    hashed_password=hash_password(settings.admin_password),
                    role=Role.admin.value,
                )
            )
            db.commit()
            log.info("seeded initial admin user", email=settings.admin_email)
