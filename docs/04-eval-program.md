# Eval Program — Stack Map & Taxonomy (Program Phases 1–2 deliverable)

The production eval program treats evaluation as an engineering asset: every LLM call is
inventoried, every quality claim has a metric, every metric has a method, and the whole
suite runs in CI. Tooling lives in [`evals/`](../evals/README.md).

## 1. Full stack map — every LLM call, agent, and loop

| # | Call site | Purpose | Model used | Loop / cap | Cost & latency tracking |
|---|---|---|---|---|---|
| 1 | `agents/graph.analyze_query_node` | spell/ambiguity fix, routing, intent (JSON) | per-request provider (default: env) | 1× per request | `rag_node_seconds{node="analyze_query"}`, tokens → `usage` |
| 2 | `agents/graph.grade_documents_node` | chunk relevance verdict | same | up to `top_k` calls × up to (1+max_rewrites) retrievals; **skippable** via `grading:false` | same, per node |
| 3 | `agents/graph.rewrite_query_node` | failed-retrieval query rewrite | same | ≤ `max_rewrites` (default 1, hard cap 3) | same |
| 4 | `agents/graph.generate_node` | grounded, cited answer | same | 1× per request | same |
| 5 | `agents/graph.generate_direct_node` | small-talk path (no retrieval) | same | 1× (exclusive with 2–4) | same |
| 6 | `llm/providers.get_embeddings` | query + chunk embeddings | FastEmbed (local CPU) by default | 1× per query; n× per ingested chunk | latency inside retrieve node; $0 |
| 7 | `evals/judge.py` | LLM-as-judge scoring (offline) | dedicated judge model | per eval row | reported in eval outputs |

**Worst case per request** (top_k=4, max_rewrites=1, grading on): 1 analyze + 8 grades + 1 rewrite + 1 generate = **11 LLM calls**. Strategy knobs exist precisely to measure what each of those buys.

**Instrumentation (implemented):**
- Tokens: `usage_metadata` accumulated across every call → `usage` object in each `/chat` response + `rag_tokens_total{provider,direction}`.
- Dollars: pricing table in `llm/pricing.py` → `usage.estimated_cost_usd` + `rag_cost_dollars_total{provider,model}` (local models = $0 API cost; GPU time shows up in latency).
- Latency: `rag_agent_seconds{provider}` end-to-end + `rag_node_seconds{node}` per component. p50/p95 via `histogram_quantile` in Grafana or `evals/run_baseline.py`.

## 2. Eval taxonomy — four layers

| Layer | Question it answers | What we measure | Where |
|---|---|---|---|
| **L1 Prompt-level** | Does this single prompt do its one job? | analyzer JSON validity rate; grader verdict agreement with humans; generation citation-format adherence | `evals/metrics.py` deterministic checks + unit tests |
| **L2 Component / agent-level** | Is each node pulling its weight? | retrieval hit-rate@k; grading precision/recall vs human labels; rewrite uplift (retrieval success after rewrite); per-node p50/p95 + tokens | `run_baseline.py` per-component sections |
| **L3 End-to-end system** | Is the whole loop right, grounded, fast, affordable? | groundedness, completeness, quality (judge), accuracy per task; cost/request; latency p50/p95 | `run_baseline.py` scorecard + RAGAS harness |
| **L4 Strategy-level** | Which model + agentic strategy wins per task? | uplift vs baseline across the model×strategy matrix; Pareto frontier of cost/quality/speed | `matrix_runner.py` + `pareto.py` |

## 3. Metric → method mapping (Program Phases 3–4)

| Task | Metric | Method |
|---|---|---|
| Extraction | field-level accuracy, completeness, hallucination rate | **deterministic** (`extraction_scores`) against gold JSON |
| Entity resolution | precision, recall, F1 | **deterministic** (`er_scores`) against gold pairs |
| Summarisation / reports | faithfulness (groundedness), completeness, quality | groundedness: deterministic proxy + **calibrated LLM-judge**; quality: LLM-judge (1–5) calibrated against practitioner labels; disagreements ≥2 points → **human-in-the-loop queue** |
| RAG Q&A (end-to-end) | groundedness, answer completeness, citation adherence | deterministic proxies every run; RAGAS (judge-based) on demand |

Gold datasets live in `evals/datasets/` + the shared `ml/evaluation/golden_dataset.jsonl`
(**this is the single golden-QA asset — extend it, don't fork it**, to avoid duplicating
the intern's dataset work). Labeling workflow: draft with the platform → practitioner
reviews/corrects → append with `"reviewed_by"` field.

## 4. Program phases → repo artifacts

| Program phase | Deliverable | Artifact |
|---|---|---|
| 1–2 map + taxonomy + instrumentation | this doc; cost/latency live | docs/04, `pricing.py`, metrics |
| 3–4 benchmarks + metric definitions | suite + definitions | `evals/` datasets, `metrics.py`, `judge.py`, `evals/README.md` |
| 5–6 baseline | scorecard + ranked bottlenecks | `run_baseline.py` → `baseline_scorecard.{json,md}` |
| 7–9 model & strategy matrix | what wins where, by how much | `matrix.yaml`, `matrix_runner.py` → `matrix_results.csv`, `matrix.md` |
| 10–11 ship + uplift + Pareto | uplift scorecard, explicit trade-offs | strategy knobs in API, `pareto.py` → `pareto.md`, re-run baseline |
| 12 durable asset | CI regression evals + handover | `ci.yml` metric tests, `eval.yml` (on-demand + weekly cron), this doc |

## 5. Stretch goals — status

- **Continuous eval on live traffic:** `query_log` already captures production questions; weekly `eval.yml` cron + `ml/drift/run_drift_job.py` cover distribution shift. Next: sample N live queries/week into a review queue for gold-labeling.
- **Cost & quality budget per agent:** `CostBudgetBurn` Prometheus alert fires when hourly spend exceeds budget; quality budget = `check_thresholds.py` gates in CI. Per-agent budgets: extend alert with `provider`/`model` labels (data already exported).
- **Automated model reselection:** re-run `matrix_runner.py` against any newly pulled Ollama model (`ollama pull` + add to `matrix.yaml`); promotion rule = beats incumbent on quality at ≤ cost. Automating the trigger (watch model registries) is roadmap.
