# evals/ — Benchmark Suite & Metric Definitions (Program Phases 3–6+)

Program overview & taxonomy: [docs/04-eval-program.md](../docs/04-eval-program.md)

```bash
pip install -r requirements-evals.txt
docker compose up -d                      # platform running, samples ingested

python run_baseline.py                    # Phases 5–6: baseline scorecard
python matrix_runner.py                   # Phases 7–9: model × strategy matrix
python pareto.py                          # Phases 10–11: cost/quality/speed frontier
pytest tests -q                           # metric unit tests (run in CI)
```

## Metric definitions

**Extraction** (`extraction_scores(gold, pred)`)
- *field accuracy* = exactly-matching fields ÷ gold fields (normalized compare)
- *completeness* = gold non-null fields the prediction filled ÷ gold non-null fields
- *hallucination rate* = predicted non-null fields that are invented or contradict gold ÷ predicted non-null fields

**Entity resolution** (`er_scores(gold_pairs, pred_pairs)`)
- *precision* = correct predicted pairs ÷ predicted pairs
- *recall* = correct predicted pairs ÷ gold pairs
- *F1* = harmonic mean

**Summarisation / RAG answers**
- *groundedness (deterministic proxy)* = answer sentences with ≥50% content-token overlap against any retrieved context ÷ sentences. Cheap, runs every time. The calibrated judge is the precise version.
- *completeness* = gold key points covered (≥60% token overlap) ÷ key points
- *citation adherence* = `[n]` citations present and within range when sources exist
- *faithfulness & quality (LLM-judge)* = 1–5 rubric scores from `judge.py`, **calibrated**: run `calibrate()` against practitioner labels; trust the judge only if within-one-point agreement ≥ 0.8, else route to human review

## Datasets (`datasets/`)

Seeds only — grow them with practitioner-reviewed rows (see labeling workflow in docs/04).

| File | Task | Gold format |
|---|---|---|
| `extraction.jsonl` | field extraction | `{"text", "gold": {field: value}}` |
| `entity_resolution.jsonl` | record matching | `{"records": [...], "gold_pairs": [[id,id],...]}` |
| `summarization.jsonl` | summaries/reports | `{"document", "key_points": [...]}` |
| `../ml/evaluation/golden_dataset.jsonl` | end-to-end RAG Q&A | **shared asset** with the RAGAS harness — one golden set, no forks |

## Outputs

- `baseline_scorecard.json` / `baseline_scorecard.md` — accuracy/cost/speed per component + ranked bottlenecks
- `matrix_results.csv` / `matrix.md` — model × strategy grid with uplift vs baseline
- `pareto.md` — configurations on the cost/quality/latency frontier (explicit trade-offs)

CI: metric unit tests run on every push (`ci.yml`); the full judge-based suite runs on demand / weekly (`eval.yml`).
