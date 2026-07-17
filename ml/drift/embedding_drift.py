"""Embedding drift detection — runnable, dependency-light (numpy + fastembed).

    python embedding_drift.py --reference ref_queries.txt --current new_queries.txt

Compares two query sets in embedding space:
  1. centroid cosine shift  — has the average topic moved?
  2. PSI over similarity-to-reference-centroid — has the distribution changed shape?

Used standalone for experiments; run_drift_job.py wires it to production data.
"""

import argparse
from pathlib import Path

import numpy as np

PSI_BINS = 10
PSI_WARN, PSI_ACT = 0.2, 0.3


def embed(texts: list[str]) -> np.ndarray:
    from fastembed import TextEmbedding

    model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return np.array(list(model.embed(texts)))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def centroid_shift(ref: np.ndarray, cur: np.ndarray) -> float:
    """1 - cos(centroids): 0 = same average topic, higher = moved."""
    return 1.0 - cosine(ref.mean(axis=0), cur.mean(axis=0))


def psi(ref_scores: np.ndarray, cur_scores: np.ndarray, bins: int = PSI_BINS) -> float:
    """Population Stability Index between two score distributions."""
    edges = np.histogram_bin_edges(np.concatenate([ref_scores, cur_scores]), bins=bins)
    ref_pct = np.histogram(ref_scores, bins=edges)[0] / max(len(ref_scores), 1)
    cur_pct = np.histogram(cur_scores, bins=edges)[0] / max(len(cur_scores), 1)
    ref_pct = np.clip(ref_pct, 1e-6, None)
    cur_pct = np.clip(cur_pct, 1e-6, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def similarity_to_centroid(vectors: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    return np.array([cosine(v, centroid) for v in vectors])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, help="txt file, one query per line")
    parser.add_argument("--current", required=True, help="txt file, one query per line")
    args = parser.parse_args()

    def read_queries(path: str) -> list[str]:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        return [line for line in lines if line.strip()]

    ref_texts = read_queries(args.reference)
    cur_texts = read_queries(args.current)

    ref, cur = embed(ref_texts), embed(cur_texts)
    ref_centroid = ref.mean(axis=0)

    shift = centroid_shift(ref, cur)
    psi_value = psi(similarity_to_centroid(ref, ref_centroid),
                    similarity_to_centroid(cur, ref_centroid))

    print(f"reference queries : {len(ref_texts)}")
    print(f"current queries   : {len(cur_texts)}")
    print(f"centroid shift    : {shift:.4f}   (0 = identical topic mix)")
    print(f"PSI               : {psi_value:.4f}   (>{PSI_WARN} investigate, >{PSI_ACT} act)")

    if psi_value > PSI_ACT or shift > 0.15:
        print("\n⚠ DRIFT DETECTED — extend the knowledge base or re-curate datasets (README).")
    elif psi_value > PSI_WARN:
        print("\n⚠ Mild drift — keep watching.")
    else:
        print("\n✓ Distributions look stable.")


if __name__ == "__main__":
    main()
