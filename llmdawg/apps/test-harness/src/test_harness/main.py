"""FastAPI test harness — runs OpenAI prompts through LLMDawg instrumentation."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import openai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from test_harness.prompts import PROMPT_MAP, PROMPTS, TestPrompt

try:
    import llmdawg
except ImportError:
    llmdawg = None

load_dotenv()

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_oai_client: openai.OpenAI | None = None


def _get_openai_client() -> openai.OpenAI:
    global _oai_client
    if _oai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")
        client = openai.OpenAI(api_key=api_key)
        if llmdawg is not None:
            llmdawg.init(
                api_key=os.environ.get("LLMDAWG_API_KEY"),
                base_url=os.environ.get("LLMDAWG_BASE_URL", "http://localhost:8000"),
            )
            client = llmdawg.wrap(client)
        _oai_client = client
    return _oai_client


def _run_prompt(prompt: TestPrompt) -> dict[str, Any]:
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=prompt.model,
        messages=[
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ],
        temperature=prompt.temperature,
        max_tokens=prompt.max_tokens,
    )
    choice = response.choices[0]
    return {
        "prompt_name": prompt.name,
        "model": response.model,
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
    if llmdawg is not None:
        llmdawg.flush(timeout=5.0)


app = FastAPI(title="LLMDawg Test Harness", lifespan=lifespan)


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
    results = []
    errors = []
    for prompt in PROMPTS:
        try:
            results.append(_run_prompt(prompt))
        except Exception as exc:
            errors.append({"prompt_name": prompt.name, "error": str(exc)})
    return {"results": results, "errors": errors}


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
