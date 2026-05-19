"""CostEngine — in-memory pricing cache with periodic refresh from PostgreSQL.

Design:
  - On first call (or after TTL), queries model_pricing WHERE effective_to IS NULL.
  - Stores prices as Decimal for exact arithmetic — no floats in billing math.
  - Refresh runs as a background asyncio task every 5 minutes.
  - estimate() returns None (not 0.00) when the model is unknown; callers
    should store NULL in cost_usd so dashboards can distinguish "free" from
    "unknown".
  - Thread-safe: the dict replacement is atomic in CPython and the refresh
    task only runs inside the asyncio event loop.

Usage (in FastAPI lifespan):
    cost_engine = CostEngine()
    await cost_engine.start()          # loads prices + schedules refresh
    ...
    await cost_engine.stop()           # cancels the refresh task

Usage (in a route):
    cost = cost_engine.estimate("openai", "gpt-4o", 100, 50, 0)
"""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal
from typing import Optional

log = logging.getLogger(__name__)

# How often to re-query the DB for pricing updates (seconds)
_REFRESH_INTERVAL = 300  # 5 minutes

# (provider, model) → (input_per_1k, output_per_1k, cached_per_1k) — all Decimal
_PriceEntry = tuple[Decimal, Decimal, Decimal]

# Dated snapshots across every major provider follow ISO YYYY-MM-DD suffix:
# OpenAI `gpt-5-mini-2025-08-07`, Anthropic `claude-3-5-sonnet-20241022` (no
# dashes handled separately below), Azure deployments echo the OpenAI suffix.
_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")
_ANTHROPIC_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")

# Managed-LLM services bill at their underlying model provider's rate card.
# When a span arrives from a managed provider without an explicit pricing
# row, fall back to the upstream provider's rate.
_PROVIDER_FALLBACKS: dict[str, str] = {
    "azure": "openai",
    "bedrock": "anthropic",
    "vertex_ai": "google",
}


class CostEngine:
    """Singleton-style service: create once and inject via app.state."""

    def __init__(self) -> None:
        self._prices: dict[tuple[str, str], _PriceEntry] = {}
        self._loaded: bool = False
        self._refresh_task: Optional[asyncio.Task[None]] = None
        self._unknown_models: set[tuple[str, str]] = set()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Load prices from DB and start the background refresh loop."""
        await self._load_from_db()
        self._refresh_task = asyncio.create_task(self._refresh_loop(), name="cost-engine-refresh")
        log.info("CostEngine started — %d pricing entries loaded", len(self._prices))

    async def stop(self) -> None:
        """Cancel the refresh task on application shutdown."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        log.info("CostEngine stopped")

    # ── Public API ────────────────────────────────────────────────────────────

    def canonicalize(self, provider: str, model: str) -> tuple[str, str]:
        """Normalize (provider, model) into the pair used for pricing lookup.

        Strips dated snapshot suffixes (e.g., `-2025-08-07`, `-20241022`) so
        `gpt-5-mini-2025-08-07` and `gpt-5-mini` share a pricing entry. The
        provider is lowercased but not rewritten — fallback to a parent
        provider (azure→openai) happens at lookup time in `estimate()` so the
        caller can still record the true origin on the span.
        """
        m = model.lower()
        m = _DATE_SUFFIX_RE.sub("", m)
        m = _ANTHROPIC_DATE_SUFFIX_RE.sub("", m)
        return provider.lower(), m

    def estimate(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> Optional[Decimal]:
        """Return the USD cost for one LLM call, or None if the model is unknown.

        Lookup order:
          1. (provider, canonical_model)
          2. (fallback_provider, canonical_model)  — e.g. azure → openai
        """
        prov, canonical = self.canonicalize(provider, model)
        entry = self._prices.get((prov, canonical))
        if entry is None:
            fallback = _PROVIDER_FALLBACKS.get(prov)
            if fallback:
                entry = self._prices.get((fallback, canonical))

        if entry is None:
            key = (prov, canonical)
            if key not in self._unknown_models:
                log.warning(
                    "CostEngine: unknown model %s/%s (canonical %s/%s) — cost_usd will be NULL",
                    provider, model, prov, canonical,
                )
                self._unknown_models.add(key)
            return None

        input_per_1k, output_per_1k, cached_per_1k = entry

        cost = (
            input_per_1k * Decimal(input_tokens) / Decimal(1000)
            + output_per_1k * Decimal(output_tokens) / Decimal(1000)
            + cached_per_1k * Decimal(cached_tokens) / Decimal(1000)
        )
        return cost.quantize(Decimal("0.00000001"))

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def model_count(self) -> int:
        return len(self._prices)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _load_from_db(self) -> None:
        """Query model_pricing and rebuild the in-memory dict."""
        try:
            from whyllm_api.database import get_session_factory
            from sqlalchemy import select, text

            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT provider, model,
                               input_cost_per_1k_tokens,
                               output_cost_per_1k_tokens,
                               COALESCE(cached_input_cost_per_1k_tokens, 0)
                        FROM model_pricing
                        WHERE effective_to IS NULL
                        ORDER BY provider, model
                        """
                    )
                )
                rows = result.fetchall()

            new_prices: dict[tuple[str, str], _PriceEntry] = {}
            for provider, model, inp, out, cached in rows:
                new_prices[(provider.lower(), model.lower())] = (
                    Decimal(str(inp)),
                    Decimal(str(out)),
                    Decimal(str(cached)),
                )

            # Atomic replacement — callers always see a consistent snapshot
            self._prices = new_prices
            self._loaded = True
            # Clear unknown-model warnings so they'll fire again if still unknown
            self._unknown_models.clear()
            log.debug("CostEngine refreshed — %d entries", len(self._prices))

        except Exception as exc:
            # Non-fatal: keep stale prices rather than crashing the service
            log.warning("CostEngine DB refresh failed (keeping stale prices): %s", exc)
            if not self._loaded:
                # On startup failure, attempt to seed from the bundled prices.json
                self._seed_from_json()

    def _seed_from_json(self) -> None:
        """Emergency fallback: load prices from a bundled prices.json.

        Looks for the copy shipped inside the package first (``whyllm_api/data/``
        — present in the Docker image), then falls back to the monorepo's
        ``packages/cost-tables/`` for local development.
        """
        try:
            import json
            from pathlib import Path

            parents = Path(__file__).resolve().parents
            candidates = [parents[1] / "data" / "prices.json"]
            if len(parents) > 5:
                candidates.append(
                    parents[5] / "packages" / "cost-tables" / "prices.json"
                )
            prices_file = next((p for p in candidates if p.exists()), None)
            if prices_file is None:
                log.warning(
                    "CostEngine: prices.json not found (looked in %s)",
                    [str(c) for c in candidates],
                )
                return

            with prices_file.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)

            new_prices: dict[tuple[str, str], _PriceEntry] = {}
            for provider, models in raw.items():
                if provider.startswith("_"):
                    continue
                for model, price in models.items():
                    # JSON prices are per 1M tokens; we store per 1K
                    new_prices[(provider.lower(), model.lower())] = (
                        Decimal(str(price["input"])) / Decimal(1000),
                        Decimal(str(price["output"])) / Decimal(1000),
                        Decimal(str(price.get("cached", 0))) / Decimal(1000),
                    )

            self._prices = new_prices
            self._loaded = True
            log.info("CostEngine seeded from prices.json — %d entries", len(new_prices))
        except Exception as exc:
            log.error("CostEngine: prices.json seed also failed: %s", exc)

    async def _refresh_loop(self) -> None:
        """Runs forever, reloading prices every _REFRESH_INTERVAL seconds."""
        while True:
            await asyncio.sleep(_REFRESH_INTERVAL)
            await self._load_from_db()
