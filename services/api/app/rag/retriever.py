"""Similarity search with scores attached to metadata (used for citations),
plus structural retrieval: rank chunks by phase_number when the user asks for
the last/final/best phase (metadata beats text similarity for superlatives)."""

import structlog
from langchain_core.documents import Document

from app.core.config import get_settings
from app.rag.vectorstore import get_client, get_vector_store

log = structlog.get_logger()


def retrieve(query: str, k: int | None = None, source: str | None = None) -> list[Document]:
    """Top-k dense retrieval. Optional `source` filter = retrieve from one document only.

    Phase 2 upgrades: hybrid (dense+sparse) search, metadata filters exposed in the API.
    """
    s = get_settings()
    k = k or s.retrieval_top_k

    qdrant_filter = None
    if source:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        qdrant_filter = Filter(
            must=[FieldCondition(key="metadata.source", match=MatchValue(value=source))]
        )

    results = get_vector_store().similarity_search_with_score(query, k=k, filter=qdrant_filter)

    docs: list[Document] = []
    for doc, score in results:
        doc.metadata["score"] = round(float(score), 4)
        docs.append(doc)
    return docs


def retrieve_by_phase_rank(k: int | None = None) -> list[Document]:
    """Chunks ordered by phase_number DESC — no embedding involved.

    Answers structure questions ("what is the final phase?") that similarity
    search fundamentally cannot. Requires the integer payload index created in
    vectorstore.get_vector_store(); chunks ingested before this feature existed
    have no phase_number and must be re-ingested to participate.
    """
    from qdrant_client.http import models as qm

    s = get_settings()
    k = k or s.retrieval_top_k
    try:
        points, _ = get_client().scroll(
            collection_name=s.qdrant_collection,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="metadata.phase_number", range=qm.Range(gte=0))]
            ),
            order_by=qm.OrderBy(key="metadata.phase_number", direction=qm.Direction.DESC),
            limit=k,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as exc:
        log.warning("phase-ranked retrieval unavailable", error=str(exc))
        return []

    docs: list[Document] = []
    for point in points:
        payload = point.payload or {}
        metadata = dict(payload.get("metadata") or {})
        metadata["retrieval"] = "phase_rank"  # visible in sources — great for demos
        docs.append(Document(page_content=payload.get("page_content", ""), metadata=metadata))
    return docs
