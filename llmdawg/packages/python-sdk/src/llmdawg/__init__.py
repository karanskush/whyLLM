"""LLMDawg Python SDK.

Quick start:
    import llmdawg
    llmdawg.init(api_key="ld-...")

    from openai import OpenAI
    client = llmdawg.wrap(OpenAI())
    response = client.chat.completions.create(...)  # automatically traced

    # Attach application context
    llmdawg.set_user("user-123")
    llmdawg.set_session("sess-abc")

    # Group related calls into a trace
    with llmdawg.trace(name="rag-pipeline", user_id="u-42", tags={"feature": "search"}):
        embedding = client.embeddings.create(...)    # traced
        completion = client.chat.completions.create(...)  # traced, same trace_id

    llmdawg.flush()
"""

from llmdawg.client import LLMDawgClient
from llmdawg.context import clear_tags, set_session, set_tags, set_user, trace
from llmdawg.tracer import flush, init, wrap

__version__ = "0.2.0"
__all__ = [
    "init",
    "wrap",
    "flush",
    "trace",
    "set_user",
    "set_session",
    "set_tags",
    "clear_tags",
    "LLMDawgClient",
    "__version__",
]
