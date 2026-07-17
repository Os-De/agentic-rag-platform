"""Model × Strategy sweep (Program Phases 7–9): what wins where, and by how much.

    python matrix_runner.py [--api http://localhost:8000] [--config matrix.yaml]

Outputs: matrix_results.csv, matrix.md (uplift vs the baseline combo).
"""

import argparse
import csv
import json
from pathlib import Path

import yaml
from common import RAG_QA_DATASET, ask, load_jsonl, login, make_client, pctl
from metrics import completeness_vs_points, sentence_groundedness

HERE = Path(__file__).parent


def run_combo(client, headers, rows, model_cfg, strategy) -> dict | None:
    grounded, complete, lats, costs = [], [], [], []
    for row in rows:
        payload = {
            "question": row["question"],
            "provider": model_cfg["provider"],
            "model": model_cfg["model"],
            **strategy["params"],
        }
        try:
            resp, latency = ask(client, headers, payload)
        except Exception as exc:  # model missing / no API key → skip combo
            print(f"  ✘ skipped ({exc})")
            return None
        contexts = [s["snippet"] for s in resp.get("sources", [])]
        grounded.append(sentence_groundedness(resp["answer"], contexts))
        complete.append(completeness_vs_points(resp["answer"], [row["ground_truth"]]))
        lats.append(latency)
        costs.append((resp.get("usage") or {}).get("estimated_cost_usd", 0.0))
    n = len(rows)
    return {
        "model": model_cfg["label"],
        "strategy": strategy["label"],
        "groundedness": round(sum(grounded) / n, 4),
        "completeness": round(sum(complete) / n, 4),
        "quality": round((sum(grounded) / n) * 0.6 + (sum(complete) / n) * 0.4, 4),
        "latency_p50_s": pctl(lats, 0.5),
        "cost_mean_usd": round(sum(costs) / n, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--config", default=str(HERE / "matrix.yaml"))
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    rows = load_jsonl(RAG_QA_DATASET)[: cfg.get("questions_limit", 8)]

    results: list[dict] = []
    with make_client(args.api) as client:
        headers = login(client)
        for model_cfg in cfg["models"]:
            for strategy in cfg["strategies"]:
                print(f"▶ {model_cfg['label']} × {strategy['label']}")
                result = run_combo(client, headers, rows, model_cfg, strategy)
                if result:
                    results.append(result)
                    print(f"  quality={result['quality']} p50={result['latency_p50_s']}s "
                          f"cost={result['cost_mean_usd']}$")

    if not results:
        raise SystemExit("No combos completed — is the stack up and models pulled?")

    baseline_model = next(
        (m["label"] for m in cfg["models"] if m.get("baseline")), cfg["models"][0]["label"]
    )
    base = next(
        (r for r in results if r["model"] == baseline_model and r["strategy"] == "baseline"),
        results[0],
    )
    for r in results:
        r["quality_uplift"] = round(r["quality"] - base["quality"], 4)
        r["latency_delta_s"] = round(r["latency_p50_s"] - base["latency_p50_s"], 3)
        r["cost_delta_usd"] = round(r["cost_mean_usd"] - base["cost_mean_usd"], 6)

    fields = list(results[0].keys())
    with (HERE / "matrix_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    best = sorted(results, key=lambda r: r["quality"], reverse=True)
    lines = [
        "# Model × Strategy Matrix (Program Phases 7–9)",
        f"\nBaseline: **{base['model']} × {base['strategy']}** "
        f"(quality {base['quality']}, p50 {base['latency_p50_s']}s, "
        f"{base['cost_mean_usd']}$/q)\n",
        "| model | strategy | quality | uplift | p50 s | Δs | $/q | Δ$ |",
        "|---|---|---|---|---|---|---|---|",
        *(
            f"| {r['model']} | {r['strategy']} | {r['quality']} | "
            f"{r['quality_uplift']:+} | {r['latency_p50_s']} | {r['latency_delta_s']:+} | "
            f"{r['cost_mean_usd']} | {r['cost_delta_usd']:+} |"
            for r in best
        ),
        "\nShip rule (Phases 10–11): adopt a combo only if quality uplift ≥ 0 at lower "
        "cost/latency, or uplift is worth the spend — then re-run run_baseline.py and "
        "python pareto.py to make the trade-off explicit.",
    ]
    (HERE / "matrix.md").write_text("\n".join(lines), encoding="utf-8")
    (HERE / "matrix_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nMatrix → {HERE / 'matrix.md'}")


if __name__ == "__main__":
    main()
