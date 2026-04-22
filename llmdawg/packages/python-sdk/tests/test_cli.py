"""Tests for the whyllm CLI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from whyllm.cli import cli


def _runner() -> CliRunner:
    return CliRunner()


class TestVerifyCommand:
    def test_verify_success_exits_0(self):
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.verify.return_value = True
            result = runner.invoke(cli, ["--api-key", "ld-test", "verify"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_verify_failure_exits_1(self):
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.verify.return_value = False
            result = runner.invoke(cli, ["--api-key", "ld-test", "verify"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_verify_uses_base_url_option(self):
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.verify.return_value = True
            instance.base_url = "http://custom:9000"
            result = runner.invoke(
                cli,
                ["--base-url", "http://custom:9000", "--api-key", "ld-test", "verify"],
            )
        MockClient.assert_called_once_with(
            api_key="ld-test", base_url="http://custom:9000"
        )
        assert result.exit_code == 0


class TestTestIngestCommand:
    def test_success_exits_0(self):
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.ingest_span.return_value = None
            result = runner.invoke(cli, ["--api-key", "ld-test", "test-ingest"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_failure_exits_1(self):
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.ingest_span.side_effect = Exception("connection refused")
            result = runner.invoke(cli, ["--api-key", "ld-test", "test-ingest"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_custom_model_and_provider(self):
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.ingest_span.return_value = None
            result = runner.invoke(
                cli,
                [
                    "--api-key", "ld-test",
                    "test-ingest",
                    "--model", "claude-3-5-sonnet-20241022",
                    "--provider", "anthropic",
                ],
            )
        assert result.exit_code == 0
        call_args = instance.ingest_span.call_args[0][0]
        assert call_args["model"] == "claude-3-5-sonnet-20241022"
        assert call_args["provider"] == "anthropic"

    def test_span_has_required_fields(self):
        runner = _runner()
        captured_span: dict = {}
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value

            def capture(span):
                captured_span.update(span)

            instance.ingest_span.side_effect = capture
            runner.invoke(cli, ["--api-key", "ld-test", "test-ingest"])

        assert "span_id" in captured_span
        assert "started_at" in captured_span
        assert "ended_at" in captured_span
        assert captured_span["status"] == "success"
        assert captured_span["source"] == "python-sdk-cli"

    def test_invalid_provider_rejected(self):
        runner = _runner()
        result = runner.invoke(
            cli,
            ["--api-key", "ld-test", "test-ingest", "--provider", "cohere"],
        )
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "Error" in result.output


class TestApiKeyFromEnv:
    def test_api_key_from_env_var(self, monkeypatch):
        monkeypatch.setenv("WHYLLM_API_KEY", "ld-env-key")
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.verify.return_value = True
            result = runner.invoke(cli, ["verify"])
        MockClient.assert_called_once_with(api_key="ld-env-key", base_url="http://localhost:8000")
        assert result.exit_code == 0

    def test_base_url_from_env_var(self, monkeypatch):
        monkeypatch.setenv("WHYLLM_BASE_URL", "http://prod:8000")
        runner = _runner()
        with patch("whyllm.cli.whyllmClient") as MockClient:
            instance = MockClient.return_value
            instance.verify.return_value = True
            runner.invoke(cli, ["--api-key", "ld-test", "verify"])
        MockClient.assert_called_once_with(api_key="ld-test", base_url="http://prod:8000")
