"""SQLAlchemy models. Vector data lives in Qdrant; Postgres holds identity,
registries, and audit/monitoring trails."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Role(enum.StrEnum):
    viewer = "viewer"      # can chat + read
    engineer = "engineer"  # + ingest documents
    admin = "admin"        # + manage users


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.viewer.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # Phase 4: soft disable
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentRecord(Base):
    """Ingestion registry — one row per uploaded document (chunks live in Qdrant)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 → dedup
    num_chunks: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    """Phase 4: privileged-action trail (logins, ingestion, user management)."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)  # e.g. "user.update"
    resource: Mapped[str] = mapped_column(String(512), default="")
    detail: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class QueryLog(Base):
    """Phase 8: production queries — the 'current window' for drift detection."""

    __tablename__ = "query_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_email: Mapped[str] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
