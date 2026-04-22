"""Global tracer — init, wrap, and flush."""

from __future__ import annotations

import logging
from typing import Any

from whyllm.client import whyllmClient
from whyllm.sender import SpanSender

log = logging.getLogger(__name__)

_client: whyllmClient | None = None
_sender: SpanSender | None = None


def init(
    api_key: str | None = None,
    base_url: str | None = None,
    max_queue: int = 1_000,
    flush_interval: float = 1.0,
) -> whyllmClient:
    """Initialize the global whyllm tracer.

    Call once at application startup before making any LLM calls.

    Args:
        api_key: Project API key (ld-...). Falls back to WHYLLM_API_KEY env var.
        base_url: Override the ingest endpoint. Defaults to http://localhost:8000.
        max_queue: Maximum spans to buffer in memory before dropping oldest.
        flush_interval: Seconds between background flush cycles.

    Returns:
        The initialized whyllmClient for advanced use cases.
    """
    global _client, _sender
    _client = whyllmClient(api_key=api_key, base_url=base_url)
    _sender = SpanSender(_client, max_queue=max_queue, flush_interval=flush_interval)
    return _client


def wrap(client: Any) -> Any:
    """Wrap a provider client to automatically trace all LLM calls.

    Supported:
        - openai.OpenAI / openai.AsyncOpenAI
        - anthropic.Anthropic / anthropic.AsyncAnthropic

    Monkey-patches the client in-place and returns it (drop-in replacement).

    Raises:
        RuntimeError: If init() has not been called yet.
        ValueError: If the client type is not supported.
    """
    if _sender is None:
        raise RuntimeError(
            "whyllm.init() must be called before whyllm.wrap(). "
            "Example: whyllm.init(api_key='ld-...')"
        )

    module = type(client).__module__
    if "openai" in module:
        from whyllm.wrappers.openai_wrapper import wrap_openai
        return wrap_openai(client, _sender)
    if "anthropic" in module:
        from whyllm.wrappers.anthropic_wrapper import wrap_anthropic
        return wrap_anthropic(client, _sender)
    raise ValueError(
        f"Unsupported client type: {type(client).__qualname__} "
        f"(module: {module}). "
        "Supported: openai.OpenAI, anthropic.Anthropic"
    )


def flush(timeout: float = 5.0) -> None:
    """Block until the span queue is drained or timeout expires.

    Call this before process exit to ensure all spans are delivered.
    Safe to call even if init() was never called.
    """
    if _sender is not None:
        _sender.flush(timeout=timeout)
