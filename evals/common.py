"""Shared helpers for the eval runners."""

import json
import os
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
RAG_QA_DATASET = HERE.parent / "ml" / "evaluation" / "golden_dataset.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def make_client(api: str) -> httpx.Client:
    return httpx.Client(base_url=api, timeout=600)


def login(client: httpx.Client, email: str | None = None, password: str | None = None) -> dict:
    r = client.post(
        "/api/v1/auth/token",
        data={
            "username": email or os.getenv("ADMIN_EMAIL", "admin@example.com"),
            "password": password or os.getenv("ADMIN_PASSWORD", "admin123"),
        },
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ask(client: httpx.Client, headers: dict, payload: dict) -> tuple[dict, float]:
    """POST /chat, returning (response_json, wall_latency_seconds)."""
    t0 = time.perf_counter()
    r = client.post("/api/v1/chat", json=payload, headers=headers)
    latency = time.perf_counter() - t0
    r.raise_for_status()
    return r.json(), latency


def pctl(values: list[float], q: float) -> float:
    """Simple percentile (q in 0..1) with linear interpolation."""
    if not values:
        return 0.0
    vals = sorted(values)
    idx = q * (len(vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(vals) - 1)
    frac = idx - lo
    return round(vals[lo] * (1 - frac) + vals[hi] * frac, 3)


def parse_node_histograms(metrics_text: str) -> dict[str, dict]:
    """Parse rag_node_seconds buckets from /metrics → per-node p50/p95/avg/count."""
    import re

    buckets: dict[str, list[tuple[float, float]]] = {}
    sums: dict[str, float] = {}
    counts: dict[str, float] = {}
    bucket_re = re.compile(r'rag_node_seconds_bucket\{le="([^"]+)",node="([^"]+)"\}\s+([\d.e+]+)')
    alt_re = re.compile(r'rag_node_seconds_bucket\{node="([^"]+)",le="([^"]+)"\}\s+([\d.e+]+)')
    for line in metrics_text.splitlines():
        m = bucket_re.search(line)
        if m:
            le, node, val = m.group(1), m.group(2), float(m.group(3))
        else:
            m = alt_re.search(line)
            if m:
                node, le, val = m.group(1), m.group(2), float(m.group(3))
            else:
                if "rag_node_seconds_sum" in line:
                    node = line.split('node="')[1].split('"')[0]
                    sums[node] = float(line.rsplit(" ", 1)[1])
                elif "rag_node_seconds_count" in line:
                    node = line.split('node="')[1].split('"')[0]
                    counts[node] = float(line.rsplit(" ", 1)[1])
                continue
        le_val = float("inf") if le == "+Inf" else float(le)
        buckets.setdefault(node, []).append((le_val, val))

    def quantile(node: str, q: float) -> float:
        bs = sorted(buckets.get(node, []))
        total = counts.get(node, bs[-1][1] if bs else 0)
        if not bs or total == 0:
            return 0.0
        target = q * total
        prev_le, prev_cum = 0.0, 0.0
        for le, cum in bs:
            if cum >= target:
                if le == float("inf"):
                    return round(prev_le, 3)
                span = cum - prev_cum
                frac = (target - prev_cum) / span if span else 0
                return round(prev_le + (le - prev_le) * frac, 3)
            prev_le, prev_cum = le, cum
        return round(prev_le, 3)

    out = {}
    for node in buckets:
        count = counts.get(node, 0)
        out[node] = {
            "count": int(count),
            "avg_s": round(sums.get(node, 0) / count, 3) if count else 0.0,
            "p50_s": quantile(node, 0.5),
            "p95_s": quantile(node, 0.95),
        }
    return out
