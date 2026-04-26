"""FastAPI test harness — runs OpenAI prompts through whyllm instrumentation."""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import whyllm
import openai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from test_harness.prompts import PROMPT_MAP, PROMPTS, TestPrompt

load_dotenv()

# Match the API's format so both services read the same in one terminal.
logging.basicConfig(
    level=os.environ.get("TEST_HARNESS_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
)
# OpenAI SDK emits the full HTTP request/response at DEBUG — flip this to see
# the raw wire traffic (headers, body, status) when debugging 401s.
if os.environ.get("OPENAI_HTTP_DEBUG", "").lower() in ("1", "true", "yes"):
    logging.getLogger("openai").setLevel(logging.DEBUG)
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logging.getLogger("httpcore").setLevel(logging.DEBUG)

log = logging.getLogger("test_harness")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_oai_client: openai.OpenAI | openai.AzureOpenAI | None = None


def _mask(value: str | None) -> str:
    """Show only the first 6 / last 4 chars of a secret for logs."""
    if not value:
        return "<unset>"
    if len(value) <= 12:
        return "***"
    return f"{value[:6]}…{value[-4:]} (len={len(value)})"


def _get_openai_client() -> openai.OpenAI | openai.AzureOpenAI:
    global _oai_client
    if _oai_client is None:
        whyllm_key = os.environ.get("WHYLLM_API_KEY")
        whyllm_base = os.environ.get("WHYLLM_BASE_URL", "http://localhost:8000")
        proxy_mode = os.environ.get("WHYLLM_PROXY_MODE", "").lower() in ("1", "true", "yes")

        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        if azure_endpoint:
            azure_key = os.environ.get("AZURE_OPENAI_API_KEY")
            if not azure_key:
                raise HTTPException(status_code=500, detail="AZURE_OPENAI_API_KEY not set")
            api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
            if proxy_mode:
                effective_endpoint = f"{whyllm_base.rstrip('/')}/proxy"
                log.info(
                    "client: AzureOpenAI via whyllm proxy | endpoint=%s api_version=%s "
                    "azure_key=%s whyllm_key=%s",
                    effective_endpoint, api_version,
                    _mask(azure_key), _mask(whyllm_key),
                )
                if not whyllm_key:
                    log.warning(
                        "client: WHYLLM_API_KEY is empty but WHYLLM_PROXY_MODE=true — "
                        "the proxy will reject with 401 (missing_api_key)",
                    )
                # Route through the unified whyllm proxy. The customer's Azure
                # upstream is stored server-side at project create time and
                # resolved from the X-whyllm-Key header — no per-request header.
                _oai_client = openai.AzureOpenAI(
                    azure_endpoint=effective_endpoint,
                    api_key=azure_key,
                    api_version=api_version,
                    default_headers={"X-whyllm-Key": whyllm_key or ""},
                )
            else:
                log.info(
                    "client: AzureOpenAI direct (SDK-wrapped) | endpoint=%s api_version=%s "
                    "azure_key=%s whyllm_key=%s",
                    azure_endpoint, api_version,
                    _mask(azure_key), _mask(whyllm_key),
                )
                whyllm.init(api_key=whyllm_key, base_url=whyllm_base)
                _oai_client = whyllm.wrap(openai.AzureOpenAI(
                    azure_endpoint=azure_endpoint,
                    api_key=azure_key,
                    api_version=api_version,
                ))
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=500,
                    detail="Set OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY",
                )
            if proxy_mode:
                base = f"{whyllm_base.rstrip('/')}/proxy/v1"
                log.info(
                    "client: OpenAI via whyllm proxy | base_url=%s openai_key=%s whyllm_key=%s",
                    base, _mask(api_key), _mask(whyllm_key),
                )
                _oai_client = openai.OpenAI(
                    api_key=api_key,
                    base_url=base,
                    default_headers={"X-whyllm-Key": whyllm_key or ""},
                )
            else:
                log.info(
                    "client: OpenAI direct (SDK-wrapped) | openai_key=%s whyllm_key=%s",
                    _mask(api_key), _mask(whyllm_key),
                )
                whyllm.init(api_key=whyllm_key, base_url=whyllm_base)
                _oai_client = whyllm.wrap(openai.OpenAI(api_key=api_key))
    return _oai_client


def _resolve_model(prompt: TestPrompt) -> str:
    if os.environ.get("AZURE_OPENAI_ENDPOINT"):
        return os.environ.get("AZURE_OPENAI_DEPLOYMENT", prompt.model)
    return prompt.model


def _run_prompt(prompt: TestPrompt, trace_id: str | None = None) -> dict[str, Any]:
    client = _get_openai_client()
    token_cap = int(os.environ.get("WHYLLM_TEST_MAX_TOKENS", "4096"))
    capped_tokens = min(prompt.max_tokens, token_cap)

    # Each prompt gets its own trace_id unless the caller supplied a batch-level
    # one (run-all shares a single trace across all N prompts so they cluster
    # together in the dashboard).
    if trace_id is None:
        trace_id = str(uuid.uuid4())

    kwargs: dict[str, Any] = {
        "model": _resolve_model(prompt),
        "messages": [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ],
        # The proxy reads X-whyllm-Trace-Id and stores it on the span — this is
        # what the /dashboard/traces grouping uses to club spans per request.
        "extra_headers": {"X-whyllm-Trace-Id": trace_id},
    }
    # gpt-5 family (Azure deployment here) rejects custom temperature and
    # uses max_completion_tokens instead of max_tokens.
    is_gpt5 = "gpt-5" in kwargs["model"].lower()
    if is_gpt5:
        kwargs["max_completion_tokens"] = capped_tokens
    else:
        kwargs["temperature"] = prompt.temperature
        kwargs["max_tokens"] = capped_tokens

    base_url = getattr(client, "base_url", None)
    log.info(
        "run: REQUEST prompt=%s model=%s max_tokens=%d trace_id=%s target=%s",
        prompt.name, kwargs["model"], capped_tokens, trace_id, base_url,
    )
    log.info(
        "run: REQUEST messages=%s",
        [(m["role"], (m["content"][:80] + "…") if len(m["content"]) > 80 else m["content"])
         for m in kwargs["messages"]],
    )

    try:
        # with_raw_response gives us HTTP headers (x-request-id, rate limits,
        # OpenAI/Azure-processing-ms) on top of the parsed body.
        raw = client.chat.completions.with_raw_response.create(**kwargs)
    except openai.APIStatusError as exc:
        body: Any
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text if exc.response is not None else None
        log.warning(
            "run: APIStatusError prompt=%s status=%s type=%s request_id=%s body=%s",
            prompt.name, exc.status_code, exc.__class__.__name__,
            exc.response.headers.get("x-request-id") if exc.response is not None else None,
            body,
        )
        raise
    except openai.APIConnectionError as exc:
        log.warning(
            "run: APIConnectionError prompt=%s target=%s err=%s",
            prompt.name, base_url, exc,
        )
        raise

    response = raw.parse()
    headers = raw.headers
    choice = response.choices[0]
    usage = response.usage

    # Validation-friendly headers from OpenAI / Azure. Not all are always set
    # (Azure emits a different subset than OpenAI), hence the .get() defaults.
    log.info(
        "run: RESPONSE id=%s model=%s finish=%s request_id=%s span_id=%s "
        "openai_processing_ms=%s azure_processing_ms=%s",
        response.id, response.model, choice.finish_reason,
        headers.get("x-request-id"),
        headers.get("x-whyllm-span-id"),  # set by our proxy if in-path
        headers.get("openai-processing-ms"),
        headers.get("x-ms-azure-processing-ms"),
    )
    if usage:
        # gpt-5 family returns completion_tokens_details.reasoning_tokens —
        # worth surfacing so the user can see "thinking" cost separately.
        reasoning = None
        details = getattr(usage, "completion_tokens_details", None)
        if details is not None:
            reasoning = getattr(details, "reasoning_tokens", None)
        log.info(
            "run: USAGE prompt_tokens=%s completion_tokens=%s total_tokens=%s "
            "reasoning_tokens=%s",
            usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
            reasoning,
        )
    log.info(
        "run: RATE-LIMIT remaining_requests=%s remaining_tokens=%s "
        "reset_requests=%s reset_tokens=%s",
        headers.get("x-ratelimit-remaining-requests"),
        headers.get("x-ratelimit-remaining-tokens"),
        headers.get("x-ratelimit-reset-requests"),
        headers.get("x-ratelimit-reset-tokens"),
    )
    content_preview = (choice.message.content or "")
    if len(content_preview) > 240:
        content_preview = content_preview[:240] + "…"
    log.info("run: CONTENT prompt=%s :: %s", prompt.name, content_preview)
    return {
        "prompt_name": prompt.name,
        "model": response.model,
        "trace_id": trace_id,
        "content": choice.message.content,
        "finish_reason": choice.finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
            "completion_tokens": response.usage.completion_tokens if response.usage else None,
            "total_tokens": response.usage.total_tokens if response.usage else None,
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    whyllm.flush(timeout=5.0)


app = FastAPI(title="whyllm Test Harness", lifespan=lifespan)


@app.get("/")
async def root():
    return RedirectResponse(url="/test", status_code=307)


@app.get("/test", response_class=HTMLResponse)
async def test_page(request: Request):
    return templates.TemplateResponse(request, "test.html", {"prompts": PROMPTS})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/run/{prompt_name}")
async def run_single(prompt_name: str):
    prompt = PROMPT_MAP.get(prompt_name)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Unknown prompt: {prompt_name}")
    return _run_prompt(prompt)


@app.post("/api/run-all")
async def run_all():
    # One trace for the whole batch — every prompt in this click shares it so
    # they render as a single collapsible group on /dashboard/traces.
    batch_trace_id = str(uuid.uuid4())
    log.info("run-all: START batch_trace_id=%s prompts=%d", batch_trace_id, len(PROMPTS))
    results = []
    errors = []
    for prompt in PROMPTS:
        try:
            results.append(_run_prompt(prompt, trace_id=batch_trace_id))
        except Exception as exc:
            errors.append({"prompt_name": prompt.name, "error": str(exc)})
    return {"results": results, "errors": errors, "trace_id": batch_trace_id}


@app.get("/api/prompts")
async def list_prompts():
    return [
        {
            "name": p.name,
            "system": p.system,
            "user": p.user,
            "model": p.model,
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
        }
        for p in PROMPTS
    ]
