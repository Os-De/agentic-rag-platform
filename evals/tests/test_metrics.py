"""Metric unit tests — run in CI on every push (Program Phase 12 regression layer)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from metrics import (  # noqa: E402
    citation_adherence,
    completeness_vs_points,
    er_scores,
    extraction_scores,
    sentence_groundedness,
)


def test_extraction_perfect():
    gold = {"invoice": "INV-1", "total": "100"}
    scores = extraction_scores(gold, {"invoice": "inv-1", "total": " 100 "})
    assert scores == {"field_accuracy": 1.0, "completeness": 1.0, "hallucination_rate": 0.0}


def test_extraction_hallucination_and_miss():
    gold = {"invoice": "INV-1", "total": "100"}
    pred = {"invoice": "INV-9", "made_up": "x"}  # wrong value + invented field, missed total
    scores = extraction_scores(gold, pred)
    assert scores["field_accuracy"] == 0.0
    assert scores["completeness"] == 0.5
    assert scores["hallucination_rate"] == 1.0


def test_er_scores():
    gold = [["a1", "a2"], ["a4", "a5"]]
    pred = [["a2", "a1"], ["a1", "a3"]]  # one correct (order-insensitive), one wrong
    scores = er_scores(gold, pred)
    assert scores["precision"] == 0.5
    assert scores["recall"] == 0.5
    assert scores["f1"] == 0.5


def test_er_empty_pred():
    assert er_scores([["a", "b"]], [])["f1"] == 0.0


def test_groundedness():
    contexts = ["The ingestion pipeline splits documents into overlapping chunks."]
    grounded = sentence_groundedness("The pipeline splits documents into chunks.", contexts)
    assert grounded == 1.0
    ungrounded = sentence_groundedness(
        "Elephants enjoy quantum snowboarding championships.", contexts
    )
    assert ungrounded == 0.0


def test_completeness_vs_points():
    answer = "It splits documents into overlapping chunks and registers uploads in PostgreSQL."
    points = ["splits into overlapping chunks", "registers uploads in PostgreSQL",
              "sends email notifications"]
    assert 0.6 < completeness_vs_points(answer, points) < 0.7  # 2 of 3


def test_citation_adherence():
    assert citation_adherence("Grounded claim [1] and another [2].", 2)
    assert not citation_adherence("Cites nothing.", 2)          # sources but no citations
    assert not citation_adherence("Out of range [5].", 2)       # citation beyond sources
    assert citation_adherence("No sources, no citations.", 0)
