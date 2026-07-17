from app.ingestion.chunking import chunk_text, extract_phase_number


def test_chunks_carry_citation_metadata():
    text = "Paragraph one about RAG.\n\n" + ("Filler sentence. " * 200)
    chunks = chunk_text(text, source="doc.md", doc_id="abc-123")

    assert len(chunks) > 1  # long text must split
    for i, chunk in enumerate(chunks):
        assert chunk.metadata["source"] == "doc.md"
        assert chunk.metadata["doc_id"] == "abc-123"
        assert chunk.metadata["chunk_index"] == i
        assert "start_index" in chunk.metadata


def test_short_text_single_chunk():
    chunks = chunk_text("tiny", source="t.txt", doc_id="x")
    assert len(chunks) == 1
    assert chunks[0].page_content == "tiny"


def test_extract_phase_number():
    assert extract_phase_number("## Phase 7 — Fine-Tuning") == 7
    assert extract_phase_number("phase 2 then PHASE 9 wins") == 9
    assert extract_phase_number("no phases here") is None
    assert extract_phase_number("phase without number") is None


def test_chunks_carry_phase_metadata():
    chunks = chunk_text("Phase 3 covers agents.", source="p.md", doc_id="d")
    assert chunks[0].metadata["phase_number"] == 3
    no_phase = chunk_text("Plain text.", source="p.md", doc_id="d")
    assert "phase_number" not in no_phase[0].metadata
