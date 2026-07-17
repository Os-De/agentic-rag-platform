"""Baseline the current pipeline (Program Phases 5–6).

    python run_baseline.py [--api http://localhost:8000] [--limit 0]

Runs the golden RAG-QA suite end-to-end against the running configuration and
produces the baseline scorecard: accuracy (deterministic proxies), cost, speed —
per component (node histograms) and for the whole loop — plus ranked bottlenecks.

Outputs: baseline_scorecard.json, baseline_scorecard.md
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from common import (
    RAG_QA_DATASET,
    ask,
    load_jsonl,
    login,
    make_client,
    parse_node_histograms,
    pctl,
)
from metrics import citation_adherence, completeness_vs_points, sentence_groundedness

HERE = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--limit", type=int, default=0, help="0 = all rows")
    args = parser.parse_args()

    rows = load_jsonl(RAG_QA_DATASET)
    if args.limit:
        rows = rows[: args.limit]

    per_q, latencies, costs, in_toks, out_toks = [], [], [], [], []
    with make_client(args.api) as client:
        headers = login(client, args.email, args.password)
        for row in rows:
            resp, latency = ask(client, headers, {"question": row["question"]})
            contexts = [s["snippet"] for s in resp.get("sources", [])]
            usage = resp.get("usage") or {}
            record = {
                "question": row["question"],
                "groundedness": sentence_groundedness(resp["answer"], contexts),
                "completeness": completeness_vs_points(resp["answer"], [row["ground_truth"]]),
                "citations_ok": citation_adherence(resp["answer"], len(contexts)),
                "rewrites": resp.get("rewrites", 0),
                "latency_s": round(latency, 2),
                "cost_usd": usage.get("estimated_cost_usd", 0.0),
                "tokens_in": usage.get("input_tokens", 0),
                "tokens_out": usage.get("output_tokens", 0),
            }
            per_q.append(record)
            latencies.append(latency)
            costs.append(record["cost_usd"])
            in_toks.append(record["tokens_in"])
            out_toks.append(record["tokens_out"])
            print(f"✔ {row['question'][:56]:58s} g={record['groundedness']:.2f} "
                  f"{record['latency_s']}s")

        node_stats = {}
        try:
            node_stats = parse_node_histograms(client.get("/metrics").text)
        except Exception as exc:
            print(f"(node histograms unavailable: {exc})")

    n = len(per_q)
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_questions": n,
        "end_to_end": {
            "groundedness_mean": round(sum(r["groundedness"] for r in per_q) / n, 4),
            "completeness_mean": round(sum(r["completeness"] for r in per_q) / n, 4),
            "citation_adherence_rate": round(sum(r["citations_ok"] for r in per_q) / n, 4),
            "latency_p50_s": pctl(latencies, 0.5),
            "latency_p95_s": pctl(latencies, 0.95),
            "cost_total_usd": round(sum(costs), 4),
            "cost_mean_usd": round(sum(costs) / n, 6),
            "tokens_mean": round((sum(in_toks) + sum(out_toks)) / n, 1),
        },
        "per_node": node_stats,
        "per_question": per_q,
    }

    (HERE / "baseline_scorecard.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    e2e = summary["end_to_end"]
    slowest = sorted(node_stats.items(), key=lambda kv: kv[1]["p95_s"], reverse=True)
    weakest = sorted(per_q, key=lambda r: r["groundedness"])[:3]
    lines = [
        "# Baseline Scorecard (Program Phases 5–6)",
        f"\nGenerated: {summary['generated_at']} · questions: {n}",
        "\n## End-to-end",
        "| metric | value |", "|---|---|",
        *(f"| {k} | {v} |" for k, v in e2e.items()),
        "\n## Per component (node latency)",
        "| node | count | avg s | p50 s | p95 s |", "|---|---|---|---|---|",
        *(f"| {node} | {s['count']} | {s['avg_s']} | {s['p50_s']} | {s['p95_s']} |"
          for node, s in slowest),
        "\n## Ranked improvement targets",
        "1. **Latency bottleneck:** "
        + (f"`{slowest[0][0]}` (p95 {slowest[0][1]['p95_s']}s)" if slowest else "n/a"),
        "2. **Weakest answers (lowest groundedness):**",
        *(f"   - {r['question'][:70]} → {r['groundedness']}" for r in weakest),
        "3. **Cost driver:** mean "
        + f"{e2e['cost_mean_usd']}$/q, {e2e['tokens_mean']} tokens/q "
        + "(grading loop dominates token count — try `grading:false` in the matrix).",
        "\nNext: `python matrix_runner.py` to hunt uplift (Phases 7–9).",
    ]
    (HERE / "baseline_scorecard.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nScorecard → {HERE / 'baseline_scorecard.md'}")


if __name__ == "__main__":
    main()
