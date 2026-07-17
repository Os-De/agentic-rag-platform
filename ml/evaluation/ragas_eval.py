"""RAGAS evaluation harness: golden dataset → live API → metrics → results files.

    python ragas_eval.py --api http://localhost:8000 [--mlflow-uri http://localhost:5000]

Outputs:
    results.json       per-question scores (inspect failures)
    eval_summary.json  metric means (consumed by check_thresholds.py / CI gate)
"""

import argparse
import json
import os
from pathlib import Path

import httpx

try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, faithfulness
except ImportError as exc:
    raise SystemExit(f"Missing deps ({exc}). Run: pip install -r requirements-eval.txt") from exc

HERE = Path(__file__).parent
METRICS = [faithfulness, answer_relevancy, context_precision]


def collect_answers(api: str, email: str, password: str) -> Dataset:
    rows = [json.loads(line) for line in (HERE / "golden_dataset.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]

    with httpx.Client(base_url=api, timeout=300) as client:
        login = client.post(
            "/api/v1/auth/token", data={"username": email, "password": password}
        )
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        records = {"question": [], "answer": [], "contexts": [], "ground_truth": []}
        for row in rows:
            r = client.post(
                "/api/v1/chat", json={"question": row["question"]}, headers=headers
            )
            r.raise_for_status()
            resp = r.json()
            records["question"].append(row["question"])
            records["answer"].append(resp["answer"])
            records["contexts"].append([s["snippet"] for s in resp["sources"]] or [""])
            records["ground_truth"].append(row["ground_truth"])
            print(f"✔ answered: {row['question'][:60]}")
    return Dataset.from_dict(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", "admin@example.com"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "admin123"))
    parser.add_argument("--mlflow-uri", default=os.getenv("MLFLOW_TRACKING_URI", ""))
    args = parser.parse_args()

    dataset = collect_answers(args.api, args.email, args.password)
    result = evaluate(dataset, metrics=METRICS)
    df = result.to_pandas()

    summary = {}
    for metric in METRICS:
        name = metric.name
        if name in df.columns:
            summary[name] = round(float(df[name].mean()), 4)

    print("\n=== RAGAS summary (means) ===")
    for name, value in summary.items():
        print(f"{name:20s} {value}")

    (HERE / "results.json").write_text(
        df.to_json(orient="records", indent=2), encoding="utf-8"
    )
    (HERE / "eval_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved → results.json, eval_summary.json")

    if args.mlflow_uri:  # Phase 6: track quality over time, compare prompts/models
        import mlflow

        mlflow.set_tracking_uri(args.mlflow_uri)
        mlflow.set_experiment("rag-quality")
        with mlflow.start_run():
            mlflow.log_metrics(summary)
            mlflow.log_artifact(str(HERE / "results.json"))
        print(f"Logged to MLflow at {args.mlflow_uri} (experiment: rag-quality)")


if __name__ == "__main__":
    main()
