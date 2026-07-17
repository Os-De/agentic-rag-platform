"""Dedup (Phase 1): identical bytes must not be re-embedded or re-registered.

Uses the SQLite test DB (see conftest) and a fake vector store — no services.
"""

import app.ingestion.service as service
from app.db.models import Base
from app.db.session import SessionLocal, engine


class FakeVectorStore:
    def __init__(self):
        self.calls = 0

    def add_documents(self, docs):
        self.calls += 1
        return [d.metadata.get("chunk_index") for d in docs]


def test_ingest_dedup(monkeypatch):
    Base.metadata.create_all(bind=engine)
    fake = FakeVectorStore()
    monkeypatch.setattr(service, "get_vector_store", lambda: fake)

    payload = b"# Notes\nPhase 1 covers ingestion and chunking."
    with SessionLocal() as db:
        first, created_first = service.ingest_bytes("notes.md", payload, "t@t.co", db)
        second, created_second = service.ingest_bytes("notes.md", payload, "t@t.co", db)

        assert created_first is True
        assert created_second is False          # dedup hit
        assert second.id == first.id            # same registry row returned
        assert fake.calls == 1                  # embedded exactly once

        # Different content → new ingestion
        third, created_third = service.ingest_bytes("notes.md", payload + b"!", "t@t.co", db)
        assert created_third is True
        assert third.id != first.id
        assert fake.calls == 2
