"""Unit tests for the cost table loader (no Docker required — pure Python)."""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Resolve the monorepo root (4 levels up from this file: tests/ → api/ → apps/ → llmdawg/)
_MONOREPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_MONOREPO_ROOT / "packages" / "cost-tables"))
from loader import compute_cost, get_price, list_models, load_prices


def test_load_prices_returns_dict() -> None:
    prices = load_prices()
    assert isinstance(prices, dict)
    assert "openai" in prices
    assert "anthropic" in prices
    assert "google" in prices


def test_get_price_known_model() -> None:
    price = get_price("openai", "gpt-4o")
    assert price["input"] == 2.50
    assert price["output"] == 10.00
    assert price["cached"] == 1.25


def test_get_price_unknown_model_raises() -> None:
    with pytest.raises(KeyError, match="No pricing found"):
        get_price("openai", "nonexistent-model-xyz")


def test_compute_cost_basic() -> None:
    # 1000 input + 500 output tokens on gpt-4o (prices are per 1M tokens)
    # input:  (1000 / 1_000_000) * 2.50  = $0.002500
    # output: (500  / 1_000_000) * 10.00 = $0.005000
    # total:                               $0.007500
    cost = compute_cost("openai", "gpt-4o", input_tokens=1000, output_tokens=500)
    assert cost == Decimal("0.00750000")


def test_compute_cost_with_cached_tokens() -> None:
    cost = compute_cost(
        "anthropic", "claude-sonnet-4-6",
        input_tokens=500, output_tokens=200, cached_tokens=300
    )
    assert isinstance(cost, Decimal)
    assert cost > 0


def test_compute_cost_returns_decimal() -> None:
    cost = compute_cost("google", "gemini-1.5-flash", input_tokens=100, output_tokens=50)
    assert isinstance(cost, Decimal)


def test_list_models() -> None:
    models = list_models()
    assert "openai" in models
    assert "gpt-4o" in models["openai"]
    assert "claude-sonnet-4-6" in models["anthropic"]
