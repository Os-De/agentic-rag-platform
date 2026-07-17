# Architecture Decision Records

Short records of *why* — the part dev ask about. Format: Context → Decision → Consequences.

## ADR-001: LangGraph as the agent framework

**Context:** Need self-correcting RAG (grade retrievals, rewrite queries, add tools later), not a linear chain.
**Decision:** LangGraph. Explicit state graph, conditional edges, checkpointing for memory, first-class LangSmith tracing.
**Consequences:** More concepts than a simple chain; in exchange, every step is inspectable and the graph grows cleanly (router, tools, human-in-the-loop).

## ADR-002: Qdrant as the vector database

**Context:** Options: Qdrant, Milvus, Weaviate, pgvector.
**Decision:** Qdrant — lightweight single container, built-in web dashboard (great for learning), payload filtering, hybrid search, generous free cloud tier for Phase 9.
**Consequences:** One more stateful service vs pgvector; Milvus offers bigger-scale features we don't need yet. Migration path documented via the thin `rag/vectorstore.py` seam.

## ADR-003: FastEmbed as default embeddings, provider-switchable

**Context:** Embeddings must work offline, free, CPU-only by default; Arabic content matters later.
**Decision:** FastEmbed (`BAAI/bge-small-en-v1.5`, 384-dim) as default; `EMBEDDING_PROVIDER` env switches to Ollama or OpenAI. Collection dimension is probed at startup, so swapping models just means a new collection.
**Consequences:** English-centric default; for Arabic corpora switch to a multilingual model (e.g., `intfloat/multilingual-e5-large`) — noted in Phase 1. Mixing models in one collection is invalid; re-ingest after switching.

## ADR-004: Multi-provider LLM abstraction (local + API)

**Context:** Requirement: local (Ollama) **and** API (OpenAI/Anthropic) models, selectable per request.
**Decision:** Thin factory (`llm/providers.py`) returning LangChain chat models; provider/model overridable in the request body, defaulted by env.
**Consequences:** Prompts must stay provider-agnostic; feature gaps (e.g., structured output support) handled with fallbacks. Enables cost/quality routing later.

## ADR-005: JWT + in-app hierarchical RBAC

**Context:** Enterprise requirement: role-based access control without heavy infra (no Keycloak yet).
**Decision:** OAuth2 password flow, HS256 JWT, roles `viewer < engineer < admin` enforced via FastAPI dependencies; users in Postgres; admin seeded from env.
**Consequences:** Simple and testable; token revocation/refresh and external IdP (OIDC) are Phase 4+ upgrades.

## ADR-006: Docker Compose with profiles

**Context:** Full stack (9+ services) is heavy for daily dev.
**Decision:** Core = `api + qdrant + postgres`. Profiles: `monitoring` (Prometheus, Grafana), `mlops` (MLflow), `ui` (Streamlit), `tracing` (Phoenix, Jaeger).
**Consequences:** Fast default startup; one file describes the whole platform; maps cleanly to managed services in Phase 9.

## ADR-007: LangSmith for LLM traces, Prometheus/Grafana for service metrics

**Context:** "Observability" spans two different questions: answer quality/agent behavior vs service health.
**Decision:** LangSmith (env-enabled, zero code) for run trees; Prometheus + Grafana for RED metrics via `prometheus-fastapi-instrumentator`.
**Consequences:** Two panes of glass, each excellent at its job. Self-hosted OTel alternatives added in ADR-011 for data-sovereignty requirements.

## ADR-008: QLoRA fine-tuning, tracked in MLflow, served via Ollama

**Context:** Consumer GPU locally; cloud GPU for larger runs; fine-tuned models must serve through the same API.
**Decision:** QLoRA (PEFT/TRL) with YAML-driven configs; params/metrics/artifacts logged to MLflow; adapters merged → GGUF → served by Ollama, so `/chat` just takes a different `model` name.
**Consequences:** Training and serving stay decoupled; promotion is gated by RAGAS evals (Phase 6), giving a real MLOps story.

## ADR-009: Pre-retrieval query analysis + structural metadata

**Context:** Real testing surfaced the failure: "What is the best **fase** to run the final?" — the typo weakened retrieval, and no chunk *textually* contains "the last phase is 9". Embeddings measure similarity, not structure.
**Decision:** (1) An `analyze_query` node runs first in the graph: spell check, ambiguity check, small-talk routing, and superlative-intent detection — corrections count in the response's rewrite flag. (2) Chunking extracts `phase_number` into Qdrant payloads with a range-indexed integer field; "last/final/best phase" questions retrieve by `order_by phase_number DESC`, fused with semantic results.
**Consequences:** One extra LLM call per request (~0.5–2s local); typos no longer poison retrieval; structure questions get structurally correct chunks. Pattern generalizes: extract any ordinal your corpus has (steps, chapters, versions).

## ADR-010: Production topology — Caddy + Compose on a VM, managed containers as alternative

**Context:** Phase 9 needs a deployable, secure-by-default production story that a single engineer can operate.
**Decision:** Primary: `docker-compose.prod.yml` — Caddy terminates TLS (automatic Let's Encrypt) and is the only exposed port; monitoring binds to localhost (SSH tunnel). Alternative: Azure Container Apps / GCP Cloud Run + Qdrant Cloud + managed Postgres (guides in `infra/`). CD: tag → GHCR images → optional cloud deploy.
**Consequences:** VM path is cheap and simple; managed path scales and patches itself. Both consume identical images, so the choice is reversible.

## ADR-011: OpenTelemetry LLM tracing (OpenInference/Phoenix + OpenLLMetry/Traceloop)

**Context:** LangSmith traces live in LangChain's cloud — a blocker when trace data (prompts, documents) must stay on-prem. The OTel ecosystem offers two vendor-neutral instrumentations for LLM apps.
**Decision:** A `TRACING_BACKEND` switch: `phoenix` uses OpenInference (TraceAI) instrumentation exporting to a self-hosted Arize Phoenix container (best LLM-native trace UI); `traceloop` uses OpenLLMetry auto-instrumentation (LangChain, OpenAI, Anthropic, Qdrant) exporting OTLP to any collector (Jaeger container included). Both ship in the `tracing` compose profile; LangSmith remains available independently via env.
**Consequences:** Traces can stay entirely on your infrastructure; one env var swaps backends; extra deps in the API image. Only one OTel backend active at a time (both set the global tracer provider).
