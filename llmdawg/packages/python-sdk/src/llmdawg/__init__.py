"""LLMDawg Python SDK.

Quick start:
    import llmdawg
    llmdawg.init(api_key="ld-...")

    # Wrap an OpenAI client
    from openai import OpenAI
    client = llmdawg.wrap(OpenAI())
    response = client.chat.completions.create(...)  # automatically traced

    # Flush before exit (optional — atexit handler does this automatically)
    llmdawg.flush()
"""

from llmdawg.client import LLMDawgClient
from llmdawg.tracer import flush, init, wrap

__version__ = "0.1.0"
__all__ = ["init", "wrap", "flush", "LLMDawgClient", "__version__"]
