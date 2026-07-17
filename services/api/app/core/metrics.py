"""Custom RAG metrics (Phase 5) — scraped from /metrics alongside HTTP metrics.

Dashboards: monitoring/grafana/provisioning/dashboards/rag-platform.json
Alerts:     monitoring/prometheus/alerts.yml
"""

from prometheus_client import Counter, Histogram

RAG_REQUESTS = Counter(
    "rag_requests_total",
    "Chat requests through the agent",
    ["provider", "outcome"],  # outcome: success | error
)

RAG_AGENT_SECONDS = Histogram(
    "rag_agent_seconds",
    "End-to-end agent latency per request",
    ["provider"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)

RAG_REWRITES = Counter(
    "rag_query_rewrites_total", "Query rewrites triggered by empty grading"
)

RAG_CORRECTIONS = Counter(
    "rag_query_corrections_total", "Spelling/ambiguity corrections by the analyzer"
)

RAG_TOP_SCORE = Histogram(
    "rag_retrieval_top_score",
    "Best similarity score per request (low = knowledge-base gap)",
    buckets=tuple(round(i / 10, 1) for i in range(11)),
)
