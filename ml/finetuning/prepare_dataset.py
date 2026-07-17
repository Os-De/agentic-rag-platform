"""Build an instruction dataset (dataset.jsonl) for QLoRA fine-tuning.

Strategy (Phase 7): generate draft Q/A pairs from your ingested documents using the
platform's own /chat API, then CURATE BY HAND. This script gives you the skeleton:
seed examples + a template for API-assisted generation.
"""

import json
from pathlib import Path

OUT = Path(__file__).parent / "dataset.jsonl"

SYSTEM = (
    "You are a precise assistant for an enterprise knowledge base. "
    "Answer concisely and cite sources."
)

# Seed examples — replace/extend with curated pairs from YOUR domain documents.
SEED_EXAMPLES = [
    {
        "user": "What does chunk overlap do in a RAG pipeline?",
        "assistant": "Overlap repeats the tail of one chunk at the start of the next so "
        "sentences crossing a boundary stay retrievable together. Too little cuts ideas "
        "in half; too much wastes storage and blurs scores.",
    },
    {
        "user": "Why must documents be re-ingested after changing the embedding model?",
        "assistant": "Each embedding model defines its own vector space with a fixed "
        "dimension; vectors from different models are not comparable, so the collection "
        "must be rebuilt.",
    },
]


def main() -> None:
    rows = [
        {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": ex["user"]},
                {"role": "assistant", "content": ex["assistant"]},
            ]
        }
        for ex in SEED_EXAMPLES
    ]
    # TODO(Phase 7): loop over chunks from Qdrant, ask the platform to draft Q/A pairs,
    # append them here, then manually review the file. Quality beats quantity.
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} examples → {OUT} (now curate and extend it!)")


if __name__ == "__main__":
    main()
