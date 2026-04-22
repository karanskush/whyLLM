"""Cost table loader — reads prices.json and exposes typed accessors.

Usage:
    from packages.cost_tables.loader import get_price, compute_cost

    price = get_price("openai", "gpt-4o")
    cost = compute_cost("openai", "gpt-4o", input_tokens=1000, output_tokens=500)
    # cost == Decimal("0.00750000")
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Optional, TypedDict

# Resolve path relative to this file so imports work regardless of cwd
_PRICES_FILE = Path(__file__).parent / "prices.json"


class ModelPrice(TypedDict):
    """Pricing for a single model in USD per 1M tokens."""

    input: float
    output: float
    cached: float


# Type alias for the full table
PriceTable = dict[str, dict[str, ModelPrice]]

_CACHE: PriceTable | None = None


def load_prices() -> PriceTable:
    """Return the full price table, loading and caching from disk on first call."""
    global _CACHE
    if _CACHE is None:
        with _PRICES_FILE.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        # Strip the metadata key — it's not a provider
        _CACHE = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _CACHE


def get_price(provider: str, model: str) -> ModelPrice:
    """Return the pricing dict for a given provider + model.

    Raises:
        KeyError: if the provider or model is not in the price table.
    """
    table = load_prices()
    try:
        return table[provider.lower()][model.lower()]
    except KeyError:
        available = {p: list(m.keys()) for p, m in table.items()}
        raise KeyError(
            f"No pricing found for {provider!r}/{model!r}. "
            f"Available: {available}"
        ) from None


def compute_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> Decimal:
    """Compute the USD cost for a single LLM call.

    Pricing is per 1M tokens, so we divide by 1_000_000.
    Uses Decimal for exact arithmetic — never use float for money.

    Args:
        provider: e.g. "openai", "anthropic", "google"
        model: e.g. "gpt-4o", "claude-sonnet-4-6"
        input_tokens: non-cached input tokens
        output_tokens: output tokens
        cached_tokens: tokens read from prompt cache (billed at cached rate)

    Returns:
        Exact cost in USD as a Decimal with 8 decimal places.
    """
    price = get_price(provider, model)

    # Work in Decimal to avoid floating-point rounding in billing
    input_cost = Decimal(str(price["input"])) * Decimal(input_tokens) / Decimal("1000000")
    output_cost = Decimal(str(price["output"])) * Decimal(output_tokens) / Decimal("1000000")
    cached_cost = Decimal(str(price["cached"])) * Decimal(cached_tokens) / Decimal("1000000")

    return (input_cost + output_cost + cached_cost).quantize(Decimal("0.00000001"))


def list_models() -> dict[str, list[str]]:
    """Return all supported providers and their model names."""
    return {provider: list(models.keys()) for provider, models in load_prices().items()}
