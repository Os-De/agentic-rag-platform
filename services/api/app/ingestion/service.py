"""Ingestion pipeline: extract → dedup check → chunk → embed+upsert (Qdrant) →
register (Postgres). Returns (record, created): created=False means the exact
same content was already ingested (Phase 1 idempotency)."""

import hashlib
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentRecord
from app.ingestion.chunking import chunk_text
from app.ingestion.loaders import extract_text
from app.rag.vectorstore import get_vector_store

log = structlog.get_logger()


def ingest_bytes(
    filename: str, data: bytes, uploaded_by: str, db: Session
) -> tuple[DocumentRecord, bool]:
    text = extract_text(filename, data)
    content_hash = hashlib.sha256(data).hexdigest()

    # Dedup: identical bytes → skip re-embedding entirely (safe to retry uploads).
    existing = db.scalar(
        select(DocumentRecord).where(DocumentRecord.content_hash == content_hash)
    )
    if existing is not None:
        log.info("dedup hit — skipping re-ingestion", file=filename, doc_id=existing.id)
        return existing, False

    doc_id = str(uuid.uuid4())
    chunks = chunk_text(text, source=filename, doc_id=doc_id)
    get_vector_store().add_documents(chunks)

    record = DocumentRecord(
        id=doc_id,
        filename=filename,
        content_hash=content_hash,
        num_chunks=len(chunks),
        uploaded_by=uploaded_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    log.info("ingested", file=filename, chunks=len(chunks), by=uploaded_by)
    return record, True
