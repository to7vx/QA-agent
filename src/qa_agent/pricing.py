"""Rough LLM cost estimation.

Prices are USD per 1M tokens (input, output), matched by longest model-string
prefix/substring. These are estimates for dashboard display — not billing —
and intentionally easy to update as provider pricing changes. Unknown models
cost 0.0 (we'd rather under-report than invent a number).
"""

from __future__ import annotations

# (input_per_mtok, output_per_mtok), keyed by a substring of the LiteLLM model
# string. Order matters: more specific keys should come first.
_PRICES: list[tuple[str, tuple[float, float]]] = [
    # Anthropic
    ("claude-opus-4", (15.0, 75.0)),
    ("claude-sonnet-4", (3.0, 15.0)),
    ("claude-haiku-4", (0.80, 4.0)),
    ("claude-3-5-sonnet", (3.0, 15.0)),
    ("claude-3-5-haiku", (0.80, 4.0)),
    ("claude-3-haiku", (0.25, 1.25)),
    # Google Gemini
    ("gemini-2.5-pro", (1.25, 10.0)),
    ("gemini-2.5-flash", (0.30, 2.50)),
    ("gemini-2.0-flash", (0.10, 0.40)),
    ("gemini-1.5-pro", (1.25, 5.0)),
    ("gemini-1.5-flash", (0.075, 0.30)),
]

_PER_MILLION = 1_000_000


def price_for(model: str) -> tuple[float, float] | None:
    """Return (input, output) USD per 1M tokens for a model, or None if unknown."""
    m = model.lower()
    for key, price in _PRICES:
        if key in m:
            return price
    return None


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate USD cost for a single call. Unknown models return 0.0."""
    price = price_for(model)
    if price is None:
        return 0.0
    in_rate, out_rate = price
    return (tokens_in * in_rate + tokens_out * out_rate) / _PER_MILLION
