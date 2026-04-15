from __future__ import annotations

import contextlib
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level OpenAI client between tests."""
    import test_harness.main as m
    m._oai_client = None
    yield
    m._oai_client = None


@pytest.fixture()
def _env():
    """Set required env vars for tests."""
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "sk-test-fake-key",
        "LLMDAWG_API_KEY": "ld-test-fake-key",
        "LLMDAWG_BASE_URL": "http://localhost:8000",
    }):
        yield


def _make_chat_response(content: str = "test response", model: str = "gpt-4o-mini"):
    """Build a mock OpenAI ChatCompletion response."""
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 20
    usage.total_tokens = 30

    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = "stop"

    resp = MagicMock()
    resp.choices = [choice]
    resp.model = model
    resp.usage = usage
    resp.id = "chatcmpl-test123"
    return resp


@pytest.fixture()
def mock_openai(_env):
    """Patch openai.OpenAI so no real API calls are made."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_chat_response()

    patches = [patch("test_harness.main.openai.OpenAI", return_value=mock_client)]
    import test_harness.main as m
    if m.llmdawg is not None:
        patches.append(patch("test_harness.main.llmdawg.init"))
        patches.append(patch("test_harness.main.llmdawg.wrap", return_value=mock_client))

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield mock_client


@pytest.fixture()
def client(mock_openai):
    """FastAPI test client with mocked OpenAI."""
    from test_harness.main import app
    return TestClient(app)
