# Evaluation (Phase 6) — RAGAS quality gates

Turn "the answers feel better" into numbers. The harness asks the live API every
question in the golden dataset and scores the results with RAGAS.

| Metric | Question it answers |
|---|---|
| Faithfulness | Is the answer supported by the retrieved context? (anti-hallucination) |
| Answer relevancy | Does the answer address the question? |
| Context precision | Are the retrieved chunks actually useful? |

## Run

```bash
pip install -r requirements-eval.txt
docker compose up -d                       # platform must be running with docs ingested
python ragas_eval.py --api http://localhost:8000
```

Notes: RAGAS uses a judge LLM — set `OPENAI_API_KEY` (default judge) or configure a
local judge. Scores land in `results.json`; log them to MLflow to compare runs.

## Your job (Phase 6)

Grow `golden_dataset.jsonl` to 20+ curated pairs **from your real documents**, then
wire a small subset into CI as a regression gate (fail build if faithfulness < 0.7).
