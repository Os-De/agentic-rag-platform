"""Cost / quality / speed Pareto frontier (Program Phases 10–11).

    python pareto.py    # reads matrix_results.csv → pareto.md

A config is ON the frontier if no other config is at least as good on ALL of
quality (higher better), cost, and latency (lower better) and strictly better on
one. Everything off the frontier is a hidden bad trade — this makes it explicit.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent


def dominates(a: dict, b: dict) -> bool:
    at_least = (
        a["quality"] >= b["quality"]
        and a["cost_mean_usd"] <= b["cost_mean_usd"]
        and a["latency_p50_s"] <= b["latency_p50_s"]
    )
    strictly = (
        a["quality"] > b["quality"]
        or a["cost_mean_usd"] < b["cost_mean_usd"]
        or a["latency_p50_s"] < b["latency_p50_s"]
    )
    return at_least and strictly


def main() -> None:
    path = HERE / "matrix_results.csv"
    if not path.exists():
        raise SystemExit("matrix_results.csv missing — run matrix_runner.py first")
    with path.open(encoding="utf-8") as f:
        rows = [
            {**r, "quality": float(r["quality"]),
             "cost_mean_usd": float(r["cost_mean_usd"]),
             "latency_p50_s": float(r["latency_p50_s"])}
            for r in csv.DictReader(f)
        ]

    frontier = [r for r in rows if not any(dominates(other, r) for other in rows)]
    frontier.sort(key=lambda r: r["cost_mean_usd"])

    lines = [
        "# Pareto Frontier — cost vs quality vs speed (Program Phases 10–11)",
        f"\n{len(frontier)} of {len(rows)} configurations are Pareto-optimal:\n",
        "| model | strategy | quality | $/q | p50 s |",
        "|---|---|---|---|---|",
        *(
            f"| {r['model']} | {r['strategy']} | {r['quality']} | "
            f"{r['cost_mean_usd']} | {r['latency_p50_s']} |"
            for r in frontier
        ),
        "\nRouting guidance: pick the cheapest frontier point that clears your quality "
        "bar per task; escalate to the next point only where it doesn't.",
        f"\nDominated (never pick): {len(rows) - len(frontier)} configs — see matrix.md.",
    ]
    (HERE / "pareto.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Pareto → {HERE / 'pareto.md'}")


if __name__ == "__main__":
    main()
