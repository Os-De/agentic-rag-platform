# Drift Detection (Phase 8)

LLM systems degrade silently: users start asking about topics your knowledge base
doesn't cover (data drift), or the meaning of "good answer" shifts (concept drift).
We monitor the **embedding distribution of production queries** against a reference
window.

## Signals implemented in `embedding_drift.py`

| Signal | Intuition |
|---|---|
| Centroid cosine shift | "Has the average topic moved?" |
| Population Stability Index (PSI) on similarity scores | "Has the shape of the distribution changed?" (PSI > 0.2 = investigate, > 0.3 = act) |

## Try it

```bash
pip install fastembed numpy
python embedding_drift.py --reference ref_queries.txt --current new_queries.txt
```

Feed two files with one query per line (e.g., copy real questions vs off-topic ones)
and watch the metrics react.

## Production job (implemented)

The API logs every question to the `query_log` table. `run_drift_job.py` compares
the last N days against `reference_queries.txt`:

```bash
pip install fastembed numpy sqlalchemy "psycopg[binary]"
python run_drift_job.py --days 7          # exit code 1 on act-level drift
```

Schedule weekly (cron / Windows Task Scheduler / GitHub Actions cron). Output goes
to `last_report.json`; the `LowRetrievalScores` Prometheus alert is the real-time
early-warning companion.

## Runbook: drift detected → what now?

1. Pull the drifted window: `SELECT question FROM query_log WHERE created_at >= now() - interval '7 days'` — read 30–50 queries.
2. Classify the gap: new topic (users need documents you don't have) vs new phrasing (same topic, different vocabulary) vs abuse/noise.
3. New topic → ingest the missing documents; new phrasing → extend `golden_dataset.jsonl` + consider fine-tuning data (Phase 7); noise → tighten rate limits.
4. After acting, refresh `reference_queries.txt` with the now-served queries and re-run the job to confirm `stable`.

Evidently is a good library upgrade when you outgrow this.
