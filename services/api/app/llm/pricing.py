"""Cost estimation (eval program, Phase 1–2): USD per **million** tokens.

Local models (Ollama) have zero API cost — their true cost is GPU time, which the
latency metrics capture. Extend this table as you adopt new models; unknown
models estimate to $0 and are flagged in the response as unpriced.
"""

# model-name prefix -> (input $/MTok, output $/MTok)
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # Anthropic
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-opus": (15.00, 75.00),
}


def estimate_cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """Longest-prefix match against the pricing table; unknown/local → 0.0."""
    if not model:
        return 0.0
    best: tuple[float, float] | None = None
    best_len = -1
    for prefix, rates in PRICING_PER_MTOK.items():
        if model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = rates, len(prefix)
    if best is None:
        return 0.0
    return round((input_tokens * best[0] + output_tokens * best[1]) / 1_000_000, 6)


def is_priced(model: str | None) -> bool:
    return bool(model) and any(model.startswith(p) for p in PRICING_PER_MTOK)
