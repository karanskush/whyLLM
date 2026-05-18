"""Prediction engine — Tier-2 batch learners.

The proxy (Tier 1) captures every LLM call at the wire level. This package is
Tier 2: it sweeps the captured `spans` on an interval and turns history into
forward-looking `insights` —

  - cost_forecast : month-to-date spend projected against budgets
  - rate_limit_eta: provider rate-limit headroom + throttling forecast
  - model_drift   : latency / error-rate / hallucination shifts vs a baseline

The orchestrator and scheduler live in `engine.py`; the scheduler runs inside
the existing ingest worker process, so there is no extra service to deploy.
"""
