"""Text → chunks with citation + structural metadata.

Chunking is THE quality lever people underestimate — experiment via
CHUNK_SIZE / CHUNK_OVERLAP in .env (Phase 1 task).

Structural metadata: embeddings only capture *text similarity* — they cannot
answer "which phase is LAST?". So we extract `phase_number` per chunk at ingest
time; superlative questions ("last/final/best phase") then rank by this field
in Qdrant instead of hoping the right words match (see retriever/graph).
"""

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings

# Matches "Phase 7", "phase 9", "PHASE 3" — extend with your own domain markers
# (e.g. "Step N", "Chapter N", version numbers) as a Phase 2 exercise.
_PHASE_RE = re.compile(r"\bphase\s+(\d{1,3})\b", re.IGNORECASE)


def extract_phase_number(text: str) -> int | None:
    """Highest phase number mentioned in the chunk, or None."""
    numbers = [int(n) for n in _PHASE_RE.findall(text)]
    return max(numbers) if numbers else None


def chunk_text(text: str, source: str, doc_id: str) -> list[Document]:
    s = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=s.chunk_size,
        chunk_overlap=s.chunk_overlap,
        add_start_index=True,  # keeps char offset — useful for highlighting later
    )
    docs = splitter.create_documents([text], metadatas=[{"source": source, "doc_id": doc_id}])
    for i, doc in enumerate(docs):
        doc.metadata["chunk_index"] = i
        phase = extract_phase_number(doc.page_content)
        if phase is not None:
            doc.metadata["phase_number"] = phase
    return docs
