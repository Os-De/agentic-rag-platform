"""Query analysis parsing — pure functions, unit-testable without an LLM.

The analyzer LLM (see ANALYZER_PROMPT) must return JSON. Small local models
sometimes wrap it in code fences or chatter, so parsing is defensive: on any
failure we fall back to the original query untouched — the pipeline never breaks
because analysis failed.
"""

import json
import re
from dataclasses import asdict, dataclass

ROUTES = ("retrieve", "direct")


@dataclass
class QueryAnalysis:
    original_question: str
    corrected_query: str
    was_corrected: bool = False
    wants_latest_phase: bool = False
    route: str = "retrieve"  # "retrieve" = search documents | "direct" = small talk

    def to_dict(self) -> dict:
        return asdict(self)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_analysis(raw: str, original_question: str) -> QueryAnalysis:
    """Extract the analyzer's JSON verdict; fall back to a no-op analysis."""
    fallback = QueryAnalysis(
        original_question=original_question, corrected_query=original_question
    )
    match = _JSON_RE.search(raw or "")
    if not match:
        return fallback
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback

    corrected = str(data.get("corrected_query") or "").strip()
    if not corrected:
        corrected = original_question

    was_corrected = bool(data.get("was_corrected")) and corrected != original_question
    route = str(data.get("route") or "retrieve").strip().lower()
    if route not in ROUTES:
        route = "retrieve"
    return QueryAnalysis(
        original_question=original_question,
        corrected_query=corrected,
        was_corrected=was_corrected,
        wants_latest_phase=bool(data.get("wants_latest_phase")),
        route=route,
    )
