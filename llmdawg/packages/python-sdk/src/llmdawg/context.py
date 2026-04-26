"""Thread-local context for attaching application-level metadata to spans.

Usage:
    # Set user/session for all calls in this thread
    llmdawg.set_user("user-123")
    llmdawg.set_session("sess-abc")
    llmdawg.set_tags({"feature": "search", "prompt_version": "v3"})

    # Or use trace() as a context manager for scoped attribution + trace linking
    with llmdawg.trace(
        name="answer-question",
        user_id="user-123",
        session_id="sess-abc",
        tags={"feature": "search"},
    ):
        # All LLM calls inside this block inherit the context
        client.chat.completions.create(...)
        client.embeddings.create(...)
"""

from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Any, Generator

# ── Context variables (work with both threads and asyncio) ────────────────────

_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("llmdawg_user_id", default=None)
_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("llmdawg_session_id", default=None)
_tags: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("llmdawg_tags", default={})
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("llmdawg_trace_id", default=None)
_parent_span_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("llmdawg_parent_span_id", default=None)
_trace_name: contextvars.ContextVar[str | None] = contextvars.ContextVar("llmdawg_trace_name", default=None)


# ── Public setters (persist until explicitly cleared) ─────────────────────────

def set_user(user_id: str | None) -> None:
    """Set the user_id for all subsequent LLM calls in this context."""
    _user_id.set(user_id)


def set_session(session_id: str | None) -> None:
    """Set the session_id for all subsequent LLM calls in this context."""
    _session_id.set(session_id)


def set_tags(tags: dict[str, Any]) -> None:
    """Merge tags into the current context. Overwrites existing keys."""
    current = _tags.get({})
    _tags.set({**current, **tags})


def clear_tags() -> None:
    """Remove all tags from the current context."""
    _tags.set({})


# ── Trace context manager ────────────────────────────────────────────────────

@contextmanager
def trace(
    name: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> Generator[str, None, None]:
    """Scope a group of LLM calls into a single trace.

    All calls made inside this block inherit the trace_id, user_id,
    session_id, and tags. Nesting is supported — inner traces get
    a new trace_id while outer context is restored on exit.

    Yields the trace_id (auto-generated if not provided).

    Example:
        with llmdawg.trace(name="rag-pipeline", user_id="u-42") as tid:
            embedding = client.embeddings.create(...)
            completion = client.chat.completions.create(...)
            # Both calls share trace_id=tid and user_id="u-42"
    """
    tid = trace_id or str(uuid.uuid4())

    # Save previous values
    prev_trace = _trace_id.set(tid)
    prev_name = _trace_name.set(name)
    prev_user = _user_id.set(user_id) if user_id is not None else None
    prev_session = _session_id.set(session_id) if session_id is not None else None

    prev_tags_token = None
    if tags:
        current = _tags.get({})
        prev_tags_token = _tags.set({**current, **tags})

    try:
        yield tid
    finally:
        _trace_id.reset(prev_trace)
        _trace_name.reset(prev_name)
        if prev_user is not None:
            _user_id.reset(prev_user)
        if prev_session is not None:
            _session_id.reset(prev_session)
        if prev_tags_token is not None:
            _tags.reset(prev_tags_token)


# ── Internal: read current context into a span dict ──────────────────────────

def get_context() -> dict[str, Any]:
    """Return a dict of context fields to merge into a span. Internal use only."""
    ctx: dict[str, Any] = {}

    uid = _user_id.get(None)
    if uid is not None:
        ctx["user_id"] = uid

    sid = _session_id.get(None)
    if sid is not None:
        ctx["session_id"] = sid

    tags = _tags.get({})
    if tags:
        ctx["tags"] = dict(tags)

    tid = _trace_id.get(None)
    if tid is not None:
        ctx["trace_id"] = tid

    name = _trace_name.get(None)
    if name is not None:
        ctx["name"] = name

    return ctx
