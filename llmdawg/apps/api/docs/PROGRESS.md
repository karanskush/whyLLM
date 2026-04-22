# whyllm — Build Progress

## Test Run Log

| Date | Scope | Pass | Fail |
|------|-------|------|------|
| 2026-04-11 | apps/api (Prompts 01–08) | 205 | 0 |
| 2026-04-11 | packages/python-sdk (Prompt 09) | 58 | 0 |

---

## Prompt Completion Status

| Prompt | Feature | Status |
|--------|---------|--------|
| 01 | Ingest pipeline (schema, endpoint, Redis queue) | ✅ Done |
| 02 | DB models, migrations, partitioned spans table | ✅ Done |
| 03 | Cost engine, pricing from DB, model catalog | ✅ Done |
| 04 | Background worker (asyncio BRPOP, hallucination scorer) | ✅ Done |
| 05 | Proxy routes (OpenAI + Anthropic, streaming, budget gate) | ✅ Done |
| 06A | Auth endpoints (register, login, JWT, /me) | ✅ Done |
| 06B | Dashboard layout, overview page, KPIs, live SSE feed | ✅ Done |
| 07 | Traces Explorer + Trace Detail (cursor pagination, Gantt) | ✅ Done |
| 08A | Cost analytics endpoint + settings CRUD (API keys, budgets, alerts) | ✅ Done |
| 08B | Dashboard cost page + settings page (tabs, API key modal) | ✅ Done |
| 09 | Python SDK (SpanSender, OpenAI patcher, Anthropic patcher, CLI) | ✅ Done |

---

## Files Created / Modified by Prompt

### Prompt 08A — API
- `apps/api/src/whyllm_api/routes/cost.py` — GET /v1/projects/:id/cost/breakdown
- `apps/api/src/whyllm_api/routes/settings.py` — CRUD for api-keys, budgets, alerts
- `apps/api/src/whyllm_api/schemas/settings.py` — request/response schemas
- `apps/api/tests/test_settings.py` — 26 tests (TestApiKeys, TestBudgets, TestAlerts, TestCostBreakdown)
- `apps/api/src/whyllm_api/main.py` — registered cost_router + settings_router

### Prompt 08B — Dashboard
- `apps/dashboard/src/app/dashboard/cost/page.tsx` — cost analytics with heatmap
- `apps/dashboard/src/app/dashboard/settings/page.tsx` — tabbed settings page
- `apps/dashboard/src/app/dashboard/settings/_components/api-keys-tab.tsx`
- `apps/dashboard/src/app/dashboard/settings/_components/budgets-tab.tsx`
- `apps/dashboard/src/app/dashboard/settings/_components/alerts-tab.tsx`
- `apps/dashboard/src/lib/api.ts` — added cost + settings namespaces + types

### Prompt 09 — Python SDK
- `packages/python-sdk/src/whyllm/wrappers/anthropic_wrapper.py` — full Anthropic patcher
- `packages/python-sdk/src/whyllm/wrappers/openai_wrapper.py` — full OpenAI patcher
- `packages/python-sdk/src/whyllm/sender.py` — SpanSender background queue
- `packages/python-sdk/src/whyllm/client.py` — whyllmClient with ingest_batch
- `packages/python-sdk/src/whyllm/tracer.py` — init(), wrap(), flush() global API
- `packages/python-sdk/src/whyllm/__init__.py` — package exports
- `packages/python-sdk/src/whyllm/cli.py` — click CLI (verify, test-ingest)
- `packages/python-sdk/pyproject.toml` — click dep + [project.scripts] entry point
- `packages/python-sdk/tests/test_sender.py` — 16 tests
- `packages/python-sdk/tests/test_openai_patcher.py` — 21 tests
- `packages/python-sdk/tests/test_anthropic_patcher.py` — 17 tests
- `packages/python-sdk/tests/test_cli.py` — 9 tests (58 total)

---

## Architecture Notes

### Security — API Keys
Raw key returned once on creation (never stored). Only `key_prefix` (12 chars) stored + returned
on subsequent reads. Key hash stored with bcrypt for SDK/proxy authentication.

### SDK — Never-raises guarantee
Every public function wraps internals in `try/except`. User apps cannot crash due to SDK.
`atexit.register(self.flush)` ensures spans drain on clean process exit.

### Streaming
Both OpenAI and Anthropic patchers wrap the raw stream object. TTFT recorded on first chunk,
span enqueued on `StopIteration`. `_finish()` is idempotent (guarded by `_finished` flag).

### Worker
Pure asyncio BRPOP consumer — no arq dependency. Reads from Redis `ingest_queue` which the
ingest route writes. Per-span pipeline: parse → cost → hallucination score → upsert → publish.
