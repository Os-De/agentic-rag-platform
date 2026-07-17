"""Qdrant access seam (see ADR-002). Everything vector-related goes through here,
so swapping the vector DB later touches one file.

Retrieval modes (Phase 2):
- dense  (default): cosine similarity over the dense embedding
- hybrid: dense + BM25 sparse vectors fused server-side by Qdrant (better recall
  for exact terms/IDs). Collections are always created hybrid-capable, so
  flipping RETRIEVAL_MODE=hybrid needs no migration for collections created by
  this version. Older dense-only collections require re-ingestion.
"""

from functools import lru_cache

import structlog
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import get_settings
from app.llm.providers import get_embeddings

log = structlog.get_logger()

SPARSE_VECTOR_NAME = "sparse"


@lru_cache
def get_client() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url)


def _collection_supports_sparse(client: QdrantClient, name: str) -> bool:
    try:
        info = client.get_collection(name)
        return bool(info.config.params.sparse_vectors)
    except Exception:
        return False


@lru_cache
def get_vector_store() -> QdrantVectorStore:
    """Create (if needed) and return the collection-backed vector store.

    Dimension is probed from the active embedding model, so changing
    EMBEDDING_* env vars + a new QDRANT_COLLECTION name = clean re-ingest.
    """
    s = get_settings()
    embeddings = get_embeddings()
    client = get_client()

    if not client.collection_exists(s.qdrant_collection):
        dim = len(embeddings.embed_query("dimension probe"))
        client.create_collection(
            collection_name=s.qdrant_collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            sparse_vectors_config={  # hybrid-capable from day one
                SPARSE_VECTOR_NAME: qm.SparseVectorParams(modifier=qm.Modifier.IDF)
            },
        )
        log.info("created qdrant collection", collection=s.qdrant_collection, dim=dim)

    # Integer payload index with range=True → enables order_by phase_number
    # (structural retrieval for "last/final/best phase" questions). Idempotent.
    try:
        client.create_payload_index(
            collection_name=s.qdrant_collection,
            field_name="metadata.phase_number",
            field_schema=qm.IntegerIndexParams(
                type=qm.IntegerIndexType.INTEGER, lookup=True, range=True
            ),
        )
    except Exception as exc:
        log.warning("payload index creation skipped", error=str(exc))

    mode = s.retrieval_mode.lower()
    if mode == "hybrid":
        if _collection_supports_sparse(client, s.qdrant_collection):
            from langchain_qdrant import FastEmbedSparse

            return QdrantVectorStore(
                client=client,
                collection_name=s.qdrant_collection,
                embedding=embeddings,
                retrieval_mode=RetrievalMode.HYBRID,
                sparse_embedding=FastEmbedSparse(model_name=s.sparse_embedding_model),
                sparse_vector_name=SPARSE_VECTOR_NAME,
            )
        log.warning(
            "RETRIEVAL_MODE=hybrid but collection has no sparse vectors — "
            "falling back to dense. Re-ingest into a fresh collection to enable hybrid."
        )

    return QdrantVectorStore(
        client=client,
        collection_name=s.qdrant_collection,
        embedding=embeddings,
    )
