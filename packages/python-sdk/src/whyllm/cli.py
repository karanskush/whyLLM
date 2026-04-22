"""whyllm CLI — verify connectivity and send test spans."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone

import click

from whyllm.client import whyllmClient


@click.group()
@click.option(
    "--api-key",
    envvar="WHYLLM_API_KEY",
    default=None,
    help="whyllm API key (or set WHYLLM_API_KEY env var).",
)
@click.option(
    "--base-url",
    envvar="WHYLLM_BASE_URL",
    default="http://localhost:8000",
    show_default=True,
    help="whyllm API base URL.",
)
@click.pass_context
def cli(ctx: click.Context, api_key: str | None, base_url: str) -> None:
    """whyllm command-line tools."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = whyllmClient(api_key=api_key, base_url=base_url)


@cli.command()
@click.pass_context
def verify(ctx: click.Context) -> None:
    """Check connectivity to the whyllm API."""
    client: whyllmClient = ctx.obj["client"]
    click.echo(f"Connecting to {client.base_url} …")
    if client.verify():
        click.secho("OK — whyllm API is reachable.", fg="green")
    else:
        click.secho(
            "FAIL — could not reach whyllm API. "
            "Check BASE_URL and that the server is running.",
            fg="red",
            err=True,
        )
        sys.exit(1)


@cli.command("test-ingest")
@click.option(
    "--model",
    default="gpt-4o-mini",
    show_default=True,
    help="Model name to include in the test span.",
)
@click.option(
    "--provider",
    default="openai",
    show_default=True,
    type=click.Choice(["openai", "anthropic"], case_sensitive=False),
    help="Provider to include in the test span.",
)
@click.pass_context
def test_ingest(ctx: click.Context, model: str, provider: str) -> None:
    """Send a single test span to verify the full ingest pipeline.

    Exits 0 on success, 1 on any error.
    """
    client: whyllmClient = ctx.obj["client"]
    now = datetime.now(tz=timezone.utc)
    span = {
        "span_id": str(uuid.uuid4()),
        "provider": provider,
        "model": model,
        "source": "python-sdk-cli",
        "status": "success",
        "started_at": now.isoformat(),
        "ended_at": now.isoformat(),
        "latency_ms": 42,
        "input_tokens": 10,
        "output_tokens": 5,
        "request": {
            "model": model,
            "messages": [{"role": "user", "content": "whyllm test-ingest ping"}],
        },
        "response": {
            "content": "pong",
            "finish_reason": "stop",
        },
    }

    click.echo(f"Sending test span to {client.base_url} …")
    try:
        client.ingest_span(span)
        click.secho("OK — test span delivered.", fg="green")
    except Exception as exc:
        click.secho(f"FAIL — {exc}", fg="red", err=True)
        sys.exit(1)


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
