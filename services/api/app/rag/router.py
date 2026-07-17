import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import run_agent
from app.auth.deps import require_role
from app.core.config import get_settings
from app.core.metrics import (
    RAG_AGENT_SECONDS,
    RAG_CORRECTIONS,
    RAG_COST_DOLLARS,
    RAG_REQUESTS,
    RAG_REWRITES,
    RAG_TOKENS,
    RAG_TOP_SCORE,
)
from app.core.ratelimit import limiter
from app.db.models import DocumentRecord, QueryLog, User
from app.db.session import get_db
from app.llm.pricing import estimate_cost_usd, is_priced
from app.rag.schemas import ChatRequest, ChatResponse, QueryAnalysisOut, SourceChunk, UsageOut

log = structlog.get_logger()
router = APIRouter(tags=["rag"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(get_settings().rate_limit_chat)
def chat(
    request: Request,  # required by slowapi
    req: ChatRequest,
    user: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Ask the agentic RAG pipeline. Provider/model switchable per request (ADR-004).
    Pass the returned conversation_id back to continue a conversation with memory."""
    provider = req.provider or get_settings().llm_provider
    log.info("chat", user=user.email, provider=provider, q=req.question[:80])

    # Fail loudly on unknown source filters (a silent no-match wastes the whole
    # rewrite loop and returns a confusing "don't know" — real user bug report).
    if req.source:
        known = db.scalar(
            select(DocumentRecord).where(DocumentRecord.filename == req.source)
        )
        if known is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"source '{req.source}' is not an ingested document — "
                "see GET /api/v1/documents for valid filenames",
            )

    started = time.perf_counter()
    try:
        result, conversation_id = run_agent(
            question=req.question,
            provider=req.provider,
            model=req.model,
            top_k=req.top_k,
            source=req.source,
            conversation_id=req.conversation_id,
            grading=req.grading,
            max_rewrites=req.max_rewrites,
        )
    except Exception as exc:  # backend (LLM/Qdrant) failures → 502, details in logs only
        RAG_REQUESTS.labels(provider=provider, outcome="error").inc()
        log.exception("agent failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream model or vector store error — check API logs.",
        ) from exc

    elapsed = time.perf_counter() - started
    RAG_REQUESTS.labels(provider=provider, outcome="success").inc()
    RAG_AGENT_SECONDS.labels(provider=provider).observe(elapsed)

    analysis_dict = result.get("analysis") or {}
    analysis = QueryAnalysisOut(**analysis_dict) if analysis_dict else None
    loop_rewrites = result.get("rewrites", 0)
    if loop_rewrites:
        RAG_REWRITES.inc(loop_rewrites)
    if analysis and analysis.was_corrected:
        RAG_CORRECTIONS.inc()

    sources = [
        SourceChunk(
            index=i,
            source=doc.metadata.get("source", "unknown"),
            chunk_index=doc.metadata.get("chunk_index"),
            phase_number=doc.metadata.get("phase_number"),
            score=doc.metadata.get("score"),
            retrieval=doc.metadata.get("retrieval"),
            snippet=doc.page_content[:240],
        )
        for i, doc in enumerate(result.get("documents", []), start=1)
    ]
    scores = [s.score for s in sources if s.score is not None]
    if scores:
        RAG_TOP_SCORE.observe(max(scores))

    # Eval program (Phase 1–2): token + cost accounting per request.
    s = get_settings()
    model_used = req.model or {
        "ollama": s.ollama_model, "openai": s.openai_model, "anthropic": s.anthropic_model
    }.get(provider, "unknown")
    tokens = result.get("tokens") or {"input": 0, "output": 0}
    cost = estimate_cost_usd(model_used, tokens["input"], tokens["output"])
    if tokens["input"] or tokens["output"]:
        RAG_TOKENS.labels