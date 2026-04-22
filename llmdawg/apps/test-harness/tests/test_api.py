"""Tests for the FastAPI endpoints."""

from unittest.mock import MagicMock


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_test_page_renders(client):
    resp = client.get("/test")
    assert resp.status_code == 200
    assert "whyllm Test Harness" in resp.text
    assert "summarise" in resp.text
    assert "Run All Prompts" in resp.text


def test_list_prompts(client):
    resp = client.get("/api/prompts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    names = {p["name"] for p in data}
    assert "summarise" in names
    assert "translate" in names


def test_run_single_success(client, mock_openai):
    resp = client.post("/api/run/summarise")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prompt_name"] == "summarise"
    assert data["content"] == "test response"
    assert data["usage"]["prompt_tokens"] == 10
    assert data["usage"]["completion_tokens"] == 20
    mock_openai.chat.completions.create.assert_called_once()


def test_run_single_unknown_prompt(client):
    resp = client.post("/api/run/nonexistent")
    assert resp.status_code == 404


def test_run_all_success(client, mock_openai):
    resp = client.post("/api/run-all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 5
    assert len(data["errors"]) == 0
    for r in data["results"]:
        assert r["content"] == "test response"


def test_run_all_with_partial_failure(client, mock_openai):
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("API quota exceeded")
        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 20
        usage.total_tokens = 30
        message = MagicMock()
        message.content = "ok"
        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        resp.model = "gpt-4o-mini"
        resp.usage = usage
        return resp

    mock_openai.chat.completions.create.side_effect = side_effect
    resp = client.post("/api/run-all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 4
    assert len(data["errors"]) == 1
    assert "quota" in data["errors"][0]["error"].lower()


def test_run_single_passes_correct_params(client, mock_openai):
    client.post("/api/run/creative")
    call_kwargs = mock_openai.chat.completions.create.call_args
    assert call_kwargs.kwargs["temperature"] == 1.0
    assert call_kwargs.kwargs["max_tokens"] == 64
    assert call_kwargs.kwargs["model"] == "gpt-4o-mini"
    messages = call_kwargs.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "haiku" in messages[1]["content"].lower()
