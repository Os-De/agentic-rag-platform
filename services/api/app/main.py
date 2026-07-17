"""Application entrypoint. Wiring only — logic lives in the feature packages."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth.admin_router import router as admin_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.ratelimit import limiter
from app.db.session import init_db
from app.ingestion.router import router as ingestion_router
from app.rag.router import router as rag_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level, json_logs=settings.environment == "prod")
    log = structlog.get_logger()

    try:
        from app.core.tracing import configure_tracing

        configure_tracing()  # OTel: phoenix / traceloop / none (ADR-011)
    except Exception as exc:
        log.warning("tracing setup failed — continuing without it", error=str(exc))

    init_db()
    log.info("database ready")

    try:
        from app.rag.vectorstore import get_vector_store

        get_vector_store()  # probes embedding dim + creates collection + payload index
        log.info("qdrant ready", collection=settings.qdrant_collection,
                 mode=settings.retrieval_mode)
    except Exception as exc:
        # Don't crash the API — /health and /auth still work; RAG endpoints will 502.
        log.warning("qdrant unavailable at startup", error=str(exc))

    log.info("startup complete", env=settings.environment, llm=settings.llm_provider)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Agentic RAG with LangGraph + Qdrant, JWT/RBAC security, "
    "multi-provider LLMs (Ollama/OpenAI/Anthropic), and full MLOps loop.",
    lifespan=lifespan,
)

# Phase 4: rate limiting (per-IP; see core/ratelimit.py for multi-worker note).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS from env: "*" in dev, exact origins in prod (Phase 9).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(ingestion_router, prefix=settings.api_v1_prefix)
app.include_router(rag_router, prefix=settings.api_v1_prefix)

# Prometheus metrics at /metrics (scraped by the monitoring profile).
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok", "name": settings.app_name, "version": settings.version}
