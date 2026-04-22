"""whyllm Python SDK.

Quick start:
    import whyllm
    whyllm.init(api_key="ld-...")

    # Wrap an OpenAI client
    from openai import OpenAI
    client = whyllm.wrap(OpenAI())
    response = client.chat.completions.create(...)  # automatically traced

    # Flush before exit (optional — atexit handler does this automatically)
    whyllm.flush()
"""

from whyllm.client import whyllmClient
from whyllm.tracer import flush, init, wrap

__version__ = "0.1.0"
__all__ = ["init", "wrap", "flush", "whyllmClient", "__version__"]
