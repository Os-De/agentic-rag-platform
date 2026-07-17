"""CI quality gate (Phase 6): fail the build if eval scores regress.

    python check_thresholds.py [--summary eval_summary.json]

Exit code 1 = block the merge. Tune thresholds as your golden dataset matures.
"""

import argparse
import json
import sys
from pathlib import Path

THRESHOLDS = {
    "faithfulness": 0.70,       # answers must be grounded in retrieved context
    "answer_relevancy": 0.70,   # answers must address the question
    "context_precision": 0.50,  # retrieval must not be mostly noise
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default=str(Path(__file__).parent / "eval_summary.json"))
    args = parser.parse_args()

    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    failures = []
    for metric, minimum in THRESHOLDS.items():
        value = summary.get(metric)
        if value is None:
            print(f"⚠ {metric}: missing from summary (skipped)")
            continue
        status = "OK " if value >= minimum else "FAIL"
        print(f"{status} {metric:20s} {value:.3f} (min {minimum})")
        if value < minimum:
            failures.append(metric)

    if failures:
        print(f"\nQuality gate FAILED: {', '.join(failures)} below threshold.")
        sys.exit(1)
    print("\nQuality gate passed.")


if __name__ == "__main__":
    main()
