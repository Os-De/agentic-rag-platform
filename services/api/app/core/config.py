"""Central configuration — 12-factor style: everything overridable via env vars / .env.

Import via `get_settings()` (cached) so tests can override env before first use.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Enterprise-Grade Agentic RAG Platform"
    version: str = "1.0.0"
    environment: str = "dev"  # dev | prod
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "*"  # comma-separated exact origins in prod (Phase 9)

    # Security
    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"  # dev seed only — override in .env
    rate_limit_login: str = "10/minute"  # slowapi syntax (Phase 4)
    rate_limit_chat: str = "30/minute"

    # Database
    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "knowledge_base"

    # LLM providers (see ADR-004)
    llm_provider: str = "ollama"  # ollama | openai | anthropic
    llm_temperature: float = 0.1
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-haiku-4-5"

    # Embeddings (see ADR-003)
    embedding_provider: str = "fastembed"  # fastembed | ollama | openai
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    ollama_embedding_model: str = "nomic-embed-text"
    openai_embedding_model: str = "text-embedding-3-small"

    # RAG tuning
    retrieval_mode: str = "dense"  # dense | hybrid (hybrid = dense + BM25 sparse fusion)
    sparse_embedding_model: str = "Qdrant/bm25"
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 4
    max_query_rewrites: int = 1
    history_max_turns: int = 6  # conversation memory kept per thread (Phase 3)

    # OpenTelemetry LLM tracing (ADR-011): none | phoenix | traceloop
    # (LangSmith is independent — enabled via LANGSMITH_* env vars.)
    tracing_backend: str = "none"
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"
    otlp_endpoint: str = "http://localhost:4318"  # traceloop → Jaeger/Tempo/any OTLP

    # Limits
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
