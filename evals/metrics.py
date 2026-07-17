"""Deterministic metrics (Program Phases 3–4). Definitions: evals/README.md.

Pure stdlib — cheap enough to run on every request/CI push. Judge-based versions
of the fuzzy metrics live in judge.py.
"""

import re

_WORD_RE = re.compile(r"[\w؀-ۿ]+")  # latin + arabic word chars
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for", "on", "with"}


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _content_tokens(text: str) -> set[str]:
    tokens = _WORD_RE.findall(text or "")
    return {t.lower() for t in tokens if len(t) > 2 and t.lower() not in _STOP}


# ── Extraction ───────────────────────────────────────────────────────────────


def extraction_scores(gold: dict, pred: dict) -> dict:
    """Field accuracy, completeness, hallucination rate. `None`/"" = null."""
    gold_fields = list(gold.keys())
    if not gold_fields:
        return {"field_accuracy": 0.0, "completeness": 0.0, "hallucination_rate": 0.0}

    def is_null(v) -> bool:
        return v is None or _norm(v) == ""

    def matches(f: str) -> bool:
        if is_null(gold[f]):
            return is_null(pred.get(f))
        return not is_null(pred.get(f)) and _norm(gold[f]) == _norm(pred.get(f))

    correct = sum(1 for f in gold_fields if matches(f))
    gold_filled = [f for f in gold_fields if not is_null(gold[f])]
    completeness = (
        sum(1 for f in gold_filled if not is_null(pred.get(f))) / len(gold_filled)
        if gold_filled else 1.0
    )
    pred_filled = [f for f in pred if not is_null(pred[f])]
    hallucinated = sum(
        1 for f in pred_filled
        if f not in gold or (is_null(gold.get(f)) and not is_null(pred[f]))
        or (not is_null(gold.get(f)) and _norm(pred[f]) != _norm(gold[f]))
    )
    return {
        "field_accuracy": round(correct / len(gold_fields), 4),
        "completeness": round(completeness, 4),
        "hallucination_rate": round(hallucinated / len(pred_filled), 4) if pred_filled else 0.0,
    }


# ── Entity resolution ────────────────────────────────────────────────────────


def er_scores(gold_pairs: list, pred_pairs: list) -> dict:
    """Precision / recall / F1 over unordered id pairs."""
    gold = {frozenset(map(str, p)) for p in gold_pairs}
    pred = {frozenset(map(str, p)) for p in pred_pairs}
    tp = len(gold & pred)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


# ── Summarisation / RAG answers ──────────────────────────────────────────────


def sentence_groundedness(answer: str, contexts: list[str], threshold: float = 0.5) -> float:
    """Fraction of answer sentences with ≥threshold content-token overlap vs any
    context. Deterministic faithfulness proxy (judge.py = precise version)."""
    sentences = [s for s in re.split(r"(?<=[.!?؟])\s+|\n+", answer or "") if _content_tokens(s)]
    if not sentences:
        return 0.0
    ctx_tokens = [_content_tokens(c) for c in contexts if c]
    if not ctx_tokens:
        return 0.0
    grounded = 0
    for sent in sentences:
        st = _content_tokens(sent)
        best = max((len(st & ct) / len(st)) for ct in ctx_tokens)
        if best >= threshold:
            grounded += 1
    return round(grounded / len(sentences), 4)


def completeness_vs_points(answer: str, key_points: list[str], threshold: float = 0.6) -> float:
    """Fraction of gold key points covered by the answer (token overlap)."""
    if not key_points:
        return 1.0
    at = _content_tokens(answer)
    covered = 0
    for point in key_points:
        pt = _content_tokens(point)
        if pt and len(pt & at) / len(pt) >= threshold:
            covered += 1
    return round(covered / len(key_points), 4)


def citation_adherence(answer: str, n_sources: int) -> bool:
    """Citations must exist and stay in range when sources exist."""
    cited = {int(m) for m in re.findall(r"\[(\d{1,2})\]", answer or "")}
    if n_sources == 0:
        return len(cited) == 0
    return bool(cited) and max(cited) <= n_sources
