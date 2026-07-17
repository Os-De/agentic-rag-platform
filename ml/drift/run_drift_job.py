"""Scheduled drift job (Phase 8): compare production queries vs the reference set.

    python run_drift_job.py [--days 7] [--database-url ...] [--min-queries 20]

Current window : query_log table (written by the API on every /chat request)
Reference set  : reference_queries.txt (what the knowledge base is SUPPOSED to cover)
Output         : last_report.json + exit code 1 on act-level drift (alert-friendly)

Schedule it: cron / Windows Task Scheduler / GitHub Actions cron — weekly is a
good start. Runbook in README.md.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # allow running from repo root
from embedding_drift import (  # noqa: E402
    PSI_ACT,
    PSI_WARN,
    centroid_shift,
    embed,
    psi,
    similarity_to_centroid,
)

HERE = Path(__file__).parent
SHIFT_ACT = 0.15


def load_current_queries(database_url: str, days: int) -> list[str]:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url, pool_pre_ping=True)
    since = datetime.now(UTC) - timedelta(days=days)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT question FROM query_log WHERE created_at >= :since"),
            {"since": since},
        ).fetchall()
    return [r[0] for r in rows if r[0] and r[0].strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "postgresql+psycopg://rag:rag@localhost:5432/rag"),
    )
    parser.add_argument("--reference", default=str(HERE / "reference_queries.txt"))
    parser.add_argument("--min-queries", type=int, default=20,
                        help="skip the check below this sample size (avoids noise)")
    args = parser.parse_args()

    ref_texts = [
        line for line in Path(args.reference).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    cur_texts = load_current_queries(args.database_url, args.days)
    print(f"reference queries: {len(ref_texts)} | production ({args.days}d): {len(cur_texts)}")

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": args.days,
        "n_reference": len(ref_texts),
        "n_current": len(cur_texts),
        "status": "insufficient_data",
        "centroid_shift": None,
        "psi": None,
    }

    if len(cur_texts) >= args.min_queries:
        ref, cur = embed(ref_texts), embed(cur_texts)
        ref_centroid = ref.mean(axis=0)
        shift = centroid_shift(ref, cur)
        psi_value = psi(
            similarity_to_centroid(ref, ref_centroid),
            similarity_to_centroid(cur, ref_centroid),
        )
        report.update(centroid_shift=round(shift, 4), psi=round(psi_value, 4))
        if psi_value > PSI_ACT or shift > SHIFT_ACT:
            report["status"] = "drift_detected"
        elif psi_value > PSI_WARN:
            report["status"] = "mild_drift"
        else:
            report["status"] = "stable"
        print(f"centroid shift: {shift:.4f} | PSI: {psi_value:.4f} → {report['status']}")
    else:
        print(f"Fewer than {args.min_queries} production queries — skipping (no verdict).")

    (HERE / "last_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Report → last_report.json")

    if report["status"] == "drift_detected":
        print("\n⚠ DRIFT DETECTED — follow the runbook in ml/drift/README.md")
        sys.exit(1)


if __name__ == "__main__":
    main()
