# Master Plan — Enterprise-Grade Agentic RAG Platform

**Status: v1.0 — all phases are implemented in code.** This document is now two things at once: the **map of what exists** (so you can study it phase by phase and explain every decision in dev) and the **backlog of operator actions + extensions** that only you can do (accounts, GPU runs, real deployment, curation).

**How to use it:** go phase by phase. For each: read the listed files until you could rebuild them, run the verification, then do the unchecked items. Commit as you go — the git history is part of the portfolio.

## Skills map

| Lead GenAI Engineer competency | Phase | Core files |
|---|---|---|
| System design & documentation | 0 | docs/, ADRs |
| Data pipelines & vector search | 1–2 | app/ingestion/, app/rag/ |
| Agent orchestration | 3 | app/agents/ |
| Secure backend engineering | 4 | app/auth/, app/core/ |
| Observability & SRE | 5 | app/core/metrics.py, monitoring/ |
| LLM evaluation & quality gates | 6 | ml/evaluation/, evals/, eval.yml |
| Fine-tuning & MLOps | 7 | ml/finetuning/ |
| Drift detection | 8 | ml/drift/, query_log |
| Cloud deployment & CI/CD | 9 | docker-compose.prod.yml, infra/, cd.yml |

---

## Phase 0 — Foundation & Tooling ✅ implemented

Monorepo layout, Docker Compose profiles, 12-factor config, structured logging, CI, ADRs.

- [ ] Run the stack, read every file in `services/api/app/core/`, explain each compose service and ADR
- [ ] `git init && git add -A && git commit -m "feat: platform v1.0"` — then push to GitHub

**Verify:** `docker compose up -d --build` → `/health` ok; `pytest services/api/tests -q` green.

## Phase 1 — Ingestion & Vector Store ✅ implemented

Loaders (txt/md/pdf/docx/html), recursive chunking with `phase_number` extraction, content-hash **dedup**, FastEmbed embeddings, Qdrant collection with payload index, document registry.

- [ ] Ingest 10+ real documents; inspect vectors + payloads in the Qdrant dashboard (:6333)
- [ ] Re-upload the same file — confirm HTTP 200 dedup (not 201) and no new vectors
- [ ] Experiment: change `CHUNK_SIZE`/`CHUNK_OVERLAP`, re-ingest, compare answer quality
- [ ] Arabic corpus: switch to `intfloat/multilingual-e5-large`, new collection, re-ingest, compare
- [ ] Extension: add a `.pptx` or `.xlsx` loader following the pattern in `loaders.py`

**Verify:** `GET /documents` accurate; typo-free questions retrieve the right chunks 9/10 times.

## Phase 2 — RAG Core ✅ implemented

Grounded, cited generation; honest "don't know"; per-request `source` filter; `top_k` control; hybrid-capable collections (`RETRIEVAL_MODE=hybrid`).

- [ ] Trace one request end-to-end in the code: router → graph → retriever → prompts
- [ ] Force the "don't know" path (ask something absent) and verify honesty
- [ ] Try `{"source": "rag_faq.md"}` filtering and compare answers
- [ ] Enable hybrid mode on a fresh collection; test exact-term queries (IDs, acronyms)

**Verify:** every grounded answer carries `[n]` citations matching `sources`.

## Phase 3 — Agentic Layer ✅ implemented

`analyze_query` (spell + ambiguity + route + intent — born from a real failure, see ADR-009), phase-ranked retrieval, structured-output grading with token fallback, rewrite loop, small-talk direct path, conversation memory (`conversation_id`), strategy knobs (`grading`, `max_rewrites`).

- [ ] Draw the graph on paper from `graph.py`, then check against architecture §4
- [ ] Ask "What is the best fase to run the final?" — watch correction + phase_rank sources
- [ ] Say "hello" — confirm the direct route (no sources, no retrieval)
- [ ] Ask a follow-up using "it" with the same `conversation_id` — memory resolves it
- [ ] Extension: add a tool node (calculator / web search) with an allowlist

**Verify:** LangSmith trace shows analyze → route decisions per node (after Phase 5 setup).

## Phase 4 — Secure Backend ✅ implemented

JWT + hierarchical RBAC, rate limiting (login + chat), audit trail + admin audit endpoint, user management (roles, disable), self-demotion guard, self-service password change, upload limits, no-enumeration login errors, non-root container.

- [ ] Create a `viewer` user; prove `/ingest` returns 403 and the attempt is audited
- [ ] Hammer `/token` 11× in a minute → 429
- [ ] Read `/admin/audit` after a session — narrate the trail
- [ ] Rotate `JWT_SECRET_KEY` + `ADMIN_PASSWORD` in `.env`
- [ ] Extension: token refresh flow; Redis storage for global rate limits

**Verify:** `pytest tests/test_rbac.py tests/test_security.py -q` green; audit rows exist.

## Phase 5 — Observability ✅ implemented

Custom metrics (provider latency, error ratio, rewrites, corrections, retrieval scores), provisioned Grafana dashboard, Prometheus alert rules, structured logs, LangSmith via env, plus self-hosted OpenTelemetry tracing (ADR-011): `TRACING_BACKEND=phoenix` (OpenInference → Phoenix) or `traceloop` (OpenLLMetry → Jaeger) with the `tracing` compose profile.

- [ ] Create a LangSmith account, set `LANGSMITH_*` in `.env`, inspect a trace per node
- [ ] `--profile monitoring` → open the auto-provisioned "RAG Platform" dashboard in Grafana
- [ ] Generate traffic; answer from dashboards only: "is it healthy? why was X slow?"
- [ ] Trigger `LowRetrievalScores` by asking 20 off-topic questions — watch the alert fire

**Verify:** you can diagnose a slow answer from LangSmith and service health from Grafana without logs.

## Phase 6 — Evaluation & LLMOps ✅ implemented

RAGAS harness → `results.json` + `eval_summary.json`, MLflow logging, threshold gate script, on-demand + weekly CI workflow (`eval.yml`).

- [ ] Grow `golden_dataset.jsonl` to 20+ pairs from YOUR documents (quality > quantity)
- [ ] Run the harness; log to MLflow (`--mlflow-uri http://localhost:5000`, `--profile mlops`)
- [ ] Change a prompt → re-run → compare runs in MLflow: regression testing for quality
- [ ] Add `OPENAI_API_KEY` repo secret; run the `RAG quality eval` workflow from the Actions tab

**Verify:** `check_thresholds.py` passes; a deliberate prompt sabotage makes it fail.

## Phase 7 — Fine-Tuning & MLOps ✅ scripts implemented — GPU runs are yours

QLoRA training (config-driven, MLflow-tracked), dataset prep, adapter merge, GGUF → Ollama serving path (`Modelfile.template`).

- [ ] Build 200+ curated instruction pairs (`prepare_dataset.py` + manual curation)
- [ ] Local GPU (WSL2): train a 1–3B model; cloud GPU (Colab/Kaggle/Azure ML): 7–8B
- [ ] `merge_adapter.py` → llama.cpp GGUF → `ollama create domain-model -f Modelfile`
- [ ] A/B with the Phase 6 harness: base vs fine-tuned — promote only on better numbers

**Verify:** `/chat` with `"model": "domain-model"` serves your fine-tune; the MLflow run reproduces it.

## Phase 8 — Drift Detection ✅ implemented

Every `/chat` question logs to `query_log`; `run_drift_job.py` compares the rolling window vs `reference_queries.txt` (centroid shift + PSI), writes `last_report.json`, exits 1 on drift; runbook in the README; `LowRetrievalScores` alert as real-time companion.

- [ ] Run the job after a week of real usage; read the report
- [ ] Simulate drift: 30 off-topic questions → job flags it → follow the runbook
- [ ] Schedule weekly (Task Scheduler / cron / GitHub Actions cron)
- [ ] Curate `reference_queries.txt` from genuinely well-served production queries

**Verify:** simulated drift is detected within one job run and the runbook resolves it.

## Phase 9 — Production & Publishing ✅ deploy pack implemented — the launch is yours

Hardened prod compose (Caddy auto-HTTPS, localhost-bound monitoring, multi-worker non-root API, healthchecks), CD workflow (tag → GHCR → optional cloud deploy + smoke test), Azure/GCP step-by-step guides.

- [ ] Pick a target: VM (`docker-compose.prod.yml`) or managed (infra/azure.md / infra/gcp.md)
- [ ] Deploy; secrets in Key Vault/Secret Manager; CORS locked to your domain
- [ ] Tag `v1.0.0` → watch CD build, push, deploy, smoke-test
- [ ] **Publish:** README demo GIF, 3-min video, blog post ("Designing an enterprise agentic RAG platform"), LinkedIn/X post
- [ ] Create 5–10 roadmap issues on GitHub (signals active ownership)

**Verify:** a stranger can use the public URL and run the repo from the README alone.

---

## Production Eval Program (12-phase initiative) ✅ implemented

The full evaluation program — stack map, 4-layer taxonomy, cost/token/node-latency
instrumentation, gold benchmarks with practitioner-review workflow, calibrated
LLM-judge, baseline scorecard, model×strategy matrix, Pareto frontier, CI regression
wiring, and stretch-goal hooks — lives in **[docs/04-eval-program.md](docs/04-eval-program.md)**
and **[evals/](evals/README.md)**. Operator loop: grow the gold datasets → `run_baseline.py`
→ `matrix_runner.py` → ship winners → `pareto.py` → re-baseline.

## Portfolio demo script (dev)

1. Architecture diagram → defend one trade-off using an ADR (ADR-009 is a great story: a real typo bug → analyzer + structural metadata).
2. Live: misspelled structural question → show correction, phase-ranked citations, rewrite flag.
3. LangSmith: walk the analyze → grade → rewrite decision tree.
4. Grafana: RED metrics + the low-retrieval-score alert as a drift early-warning.
5. MLflow: base vs fine-tuned RAGAS comparison; explain the promotion gate.
6. Close: CD pipeline + audit log — "quality and security are enforced, not hoped for."

## Publishing checklist

- [ ] No secrets in git history; fresh `JWT_SECRET_KEY`/passwords in prod
- [ ] `docker compose up` works on a clean machine
- [ ] Demo video + GIF linked in README
- [ ] Architecture diagrams render on GitHub
- [ ] Issues tab populated with roadmap items
