"use client";

import { useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import {
  Terminal,
  Key,
  CheckCircle2,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Zap,
  Code2,
  Layers,
  Users,
  Tag,
  GitBranch,
  Sparkles,
} from "lucide-react";

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="absolute top-2 right-2 p-1.5 rounded bg-zinc-700 hover:bg-zinc-600 transition-colors"
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-emerald-400" />
      ) : (
        <Copy className="w-3.5 h-3.5 text-zinc-400" />
      )}
    </button>
  );
}

// ── Code block ────────────────────────────────────────────────────────────────

function CodeBlock({ code, lang = "bash" }: { code: string; lang?: string }) {
  return (
    <div className="relative mt-3 rounded-lg bg-zinc-950 border border-zinc-800 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800">
        <span className="text-xs text-zinc-500 font-mono">{lang}</span>
      </div>
      <pre className="px-4 py-3 overflow-x-auto text-sm text-zinc-300 whitespace-pre">
        <code>{code}</code>
      </pre>
      <CopyButton text={code} />
    </div>
  );
}

// ── AI prompt constant ───────────────────────────────────────────────────────

const AI_INTEGRATION_PROMPT = `Integrate LLMDawg observability into this project. Follow these steps exactly:

1. Create and switch to a new git branch:
   git checkout -b whyllm-integration

2. Install the SDK:
   pip install llmdawg
   (or add "llmdawg" to requirements.txt / pyproject.toml dependencies)

3. Find every file that creates an OpenAI or Anthropic client. Look for patterns like:
   - client = OpenAI(...)
   - client = anthropic.Anthropic(...)
   - openai.OpenAI(...)
   - Any variable assigned to an OpenAI() or Anthropic() instance

4. In the main entry point of the app (e.g. main.py, app.py, manage.py, or wherever the app boots), add this near the top — ONCE, before any LLM client is created:

   import llmdawg
   llmdawg.init()  # reads LLMDAWG_API_KEY from env automatically

5. For EVERY OpenAI or Anthropic client instantiation you found in step 3, wrap it:

   # Before:
   client = OpenAI()
   # After:
   client = llmdawg.wrap(OpenAI())

   # Before:
   client = anthropic.Anthropic()
   # After:
   client = llmdawg.wrap(anthropic.Anthropic())

   Do NOT change any of the existing .create() calls, parameters, or response handling.
   The wrap() call is a drop-in — everything else stays identical.

6. If the project has a shutdown hook or lifespan handler (FastAPI lifespan, atexit, Django signal), add:
   llmdawg.flush(timeout=10)

   If there is no shutdown hook, add this at the end of the entry point:
   import atexit
   atexit.register(llmdawg.flush)

7. If you find any request handler or API route that serves end users, add user identification at the top of the handler:
   llmdawg.set_user(current_user.id)  # or however the app gets the user ID

8. Commit the changes:
   git add -A
   git commit -m "feat: integrate LLMDawg observability SDK"

Rules:
- Do NOT change any existing LLM call parameters, prompts, or response handling
- Do NOT modify any business logic
- Do NOT add try/except around the llmdawg calls — the SDK never raises
- The llmdawg.init() call must happen BEFORE any llmdawg.wrap() calls
- If a file creates multiple clients, wrap each one
- If a client is created inside a function, wrap it in that function (ensure llmdawg.init() was called before)`;

// ── Collapsible section ───────────────────────────────────────────────────────

function Section({
  title,
  subtitle,
  children,
  defaultOpen = false,
  icon,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  icon?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-zinc-800/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          {icon}
          <div>
            <p className="text-sm font-semibold text-white">{title}</p>
            <p className="text-xs text-zinc-500 mt-0.5">{subtitle}</p>
          </div>
        </div>
        {open ? (
          <ChevronDown className="w-4 h-4 text-zinc-500 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-zinc-500 flex-shrink-0" />
        )}
      </button>
      {open && <div className="px-6 pb-6 border-t border-zinc-800">{children}</div>}
    </div>
  );
}

// ── Step badge ────────────────────────────────────────────────────────────────

function StepBadge({ n }: { n: number }) {
  return (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-lime-500 text-black text-xs font-bold flex-shrink-0">
      {n}
    </span>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OnboardingGuidePage() {
  return (
    <div>
      <Topbar title="Setup Guide" />

      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">

        {/* Intro */}
        <div className="bg-lime-500/10 border border-lime-500/20 rounded-xl px-6 py-5">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-lime-400" />
            <span className="text-sm font-semibold text-lime-300">
              3 lines of code. Every detail captured.
            </span>
          </div>
          <p className="text-sm text-zinc-400">
            The LLMDawg SDK wraps your OpenAI and Anthropic clients in-place.
            Every LLM call is automatically traced &mdash; tokens, cost, latency,
            prompts, tool calls, cache hits, and errors &mdash; with zero changes
            to your application code.
          </p>
        </div>

        {/* ── AI Prompt — one-click integration ─────────────────────────── */}
        <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl overflow-hidden">
          <div className="px-6 py-5">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-4 h-4 text-violet-400" />
              <span className="text-sm font-semibold text-violet-300">
                Using an AI editor? Paste this prompt and you&apos;re done.
              </span>
            </div>
            <p className="text-sm text-zinc-400 mb-4">
              Copy the prompt below into{" "}
              <strong className="text-zinc-300">Claude Code</strong>,{" "}
              <strong className="text-zinc-300">Cursor</strong>,{" "}
              <strong className="text-zinc-300">Windsurf</strong>, or any AI coding assistant.
              It will find every OpenAI and Anthropic client in your codebase, wrap them
              with LLMDawg, create a <code className="text-xs bg-zinc-800 text-violet-300 px-1 rounded">whyllm-integration</code> branch,
              and commit &mdash; no manual work.
            </p>
            <div className="relative rounded-lg bg-zinc-950 border border-zinc-800 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800">
                <span className="text-xs text-zinc-500 font-mono">prompt</span>
                <span className="text-xs text-violet-400/60">works with Claude Code, Cursor, Windsurf, Copilot</span>
              </div>
              <pre className="px-4 py-3 overflow-x-auto text-sm text-zinc-300 whitespace-pre max-h-64 overflow-y-auto">
                <code>{AI_INTEGRATION_PROMPT}</code>
              </pre>
              <CopyButton text={AI_INTEGRATION_PROMPT} />
            </div>
            <div className="mt-3 flex items-start gap-2 bg-violet-500/5 border border-violet-500/10 rounded-lg px-3 py-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-violet-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-zinc-500">
                After it runs, set your key with{" "}
                <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">export LLMDAWG_API_KEY=ld-prod_...</code>{" "}
                and start your app. Traces appear in the dashboard within seconds.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-zinc-800" />
          <span className="text-xs text-zinc-600 font-medium">or set it up manually</span>
          <div className="h-px flex-1 bg-zinc-800" />
        </div>

        {/* ── Step 1: Install ──────────────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={1} />
            <div>
              <p className="text-sm font-semibold text-white">Install the SDK</p>
              <p className="text-xs text-zinc-500">One package, no extra dependencies</p>
            </div>
            <Terminal className="w-4 h-4 text-zinc-700 ml-auto" />
          </div>
          <CodeBlock lang="bash" code="pip install llmdawg" />
        </div>

        {/* ── Step 2: Get API key ─────────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={2} />
            <div>
              <p className="text-sm font-semibold text-white">Get your API key</p>
              <p className="text-xs text-zinc-500">Settings &rarr; API Keys &rarr; New Key</p>
            </div>
            <Key className="w-4 h-4 text-zinc-700 ml-auto" />
          </div>
          <p className="text-sm text-zinc-400 mb-3">
            Go to{" "}
            <a href="/dashboard/settings" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">
              Settings &rarr; API Keys
            </a>{" "}
            and click <strong className="text-zinc-200">New Key</strong>. Copy it
            immediately &mdash; it is shown only once.
          </p>
          <CodeBlock lang="bash" code="export LLMDAWG_API_KEY=ld-prod_your_key_here" />
        </div>

        {/* ── Step 3: Init + Wrap ─────────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={3} />
            <div>
              <p className="text-sm font-semibold text-white">Init and wrap your client</p>
              <p className="text-xs text-zinc-500">3 lines at the top of your app &mdash; everything else stays the same</p>
            </div>
            <Code2 className="w-4 h-4 text-zinc-700 ml-auto" />
          </div>

          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mt-2 mb-1">OpenAI</p>
          <CodeBlock
            lang="python"
            code={`import llmdawg
from openai import OpenAI

llmdawg.init()  # reads LLMDAWG_API_KEY from env
client = llmdawg.wrap(OpenAI())

# That's it. Use the client exactly as before.
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# Embeddings are automatically captured too
embedding = client.embeddings.create(
    model="text-embedding-3-small",
    input="search query",
)`}
          />

          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mt-5 mb-1">Anthropic</p>
          <CodeBlock
            lang="python"
            code={`import llmdawg
import anthropic

llmdawg.init()
client = llmdawg.wrap(anthropic.Anthropic())

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.content[0].text)`}
          />

          <div className="mt-4 bg-zinc-800/50 border border-zinc-700 rounded-lg px-4 py-3">
            <p className="text-xs font-semibold text-zinc-300 mb-2">What gets captured automatically:</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {[
                "Full prompt & response",
                "Token counts (input/output)",
                "Prompt cache hits",
                "Cost in USD",
                "Latency & time to first token",
                "Tool / function calls",
                "Model & provider",
                "Errors & status codes",
                "Streaming token counts",
                "Embedding dimensions",
              ].map((item) => (
                <div key={item} className="flex items-center gap-1.5">
                  <CheckCircle2 className="w-3 h-3 text-lime-500 flex-shrink-0" />
                  <span className="text-xs text-zinc-400">{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Step 4: Verify ──────────────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={4} />
            <div>
              <p className="text-sm font-semibold text-white">Verify it works</p>
              <p className="text-xs text-zinc-500">Run your app, then check Traces</p>
            </div>
            <CheckCircle2 className="w-4 h-4 text-zinc-700 ml-auto" />
          </div>
          <p className="text-sm text-zinc-400 mb-3">
            Make any LLM call from your app. Then open{" "}
            <a href="/dashboard/traces" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">
              Traces
            </a>{" "}
            &mdash; your call should appear within 1&ndash;2 seconds with full details.
          </p>
          <CodeBlock
            lang="python"
            code={`# Quick test — run this script
import llmdawg
from openai import OpenAI

llmdawg.init()
client = llmdawg.wrap(OpenAI())

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say hello in one word"}],
)
print(resp.choices[0].message.content)
llmdawg.flush()  # ensure spans are sent before script exits
# Now check the Traces tab in LLMDawg`}
          />
        </div>

        {/* ── Done banner ─────────────────────────────────────────────────── */}
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-6 py-5 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-emerald-300">You&apos;re capturing everything.</p>
            <p className="text-sm text-zinc-400 mt-1">
              Every LLM call flows into{" "}
              <a href="/dashboard/traces" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">Traces</a>,
              costs roll up in{" "}
              <a href="/dashboard/cost" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">Cost</a>,
              and the{" "}
              <a href="/dashboard" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">Overview</a>{" "}
              shows live activity. Read on to unlock deeper insights.
            </p>
          </div>
        </div>

        {/* ────────────────────────────────────────────────────────────────── */}
        {/* GOING DEEPER                                                      */}
        {/* ────────────────────────────────────────────────────────────────── */}

        <div className="pt-2">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">
            Go deeper &mdash; optional but powerful
          </p>
        </div>

        {/* ── Identify users ──────────────────────────────────────────────── */}
        <Section
          title="Identify users and sessions"
          subtitle={'Answer "who is costing us the most?" and "which conversation went wrong?"'}
          icon={<Users className="w-4 h-4 text-lime-500 flex-shrink-0" />}
          defaultOpen={false}
        >
          <p className="text-sm text-zinc-400 mt-4 mb-1">
            Set the user and session once &mdash; every LLM call after that inherits them.
          </p>
          <CodeBlock
            lang="python"
            code={`import llmdawg

# Set at the start of a request / handler
llmdawg.set_user(current_user.id)           # e.g. "user-42"
llmdawg.set_session(conversation.id)        # e.g. "sess-abc-123"

# All subsequent LLM calls carry this context
response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
)
# In the dashboard: filter traces by user, see per-user cost breakdown`}
          />
          <p className="text-xs text-zinc-600 mt-3">
            Works with both threads and async &mdash; uses Python contextvars under the hood.
          </p>
        </Section>

        {/* ── Tag calls ───────────────────────────────────────────────────── */}
        <Section
          title="Tag calls by feature, prompt version, or A/B variant"
          subtitle={'Slice your dashboard: "search costs 4x more than summarize"'}
          icon={<Tag className="w-4 h-4 text-lime-500 flex-shrink-0" />}
          defaultOpen={false}
        >
          <CodeBlock
            lang="python"
            code={`import llmdawg

llmdawg.set_tags({
    "feature": "search",
    "prompt_version": "v3.2",
    "ab_variant": "B",
    "environment": "production",
})

# Tags are attached to every span until cleared
response = client.chat.completions.create(...)

# Clear when done
llmdawg.clear_tags()`}
          />
        </Section>

        {/* ── Trace groups ────────────────────────────────────────────────── */}
        <Section
          title="Group related calls into a trace"
          subtitle="Link embedding + completion + tool calls into one logical unit"
          icon={<GitBranch className="w-4 h-4 text-lime-500 flex-shrink-0" />}
          defaultOpen={false}
        >
          <p className="text-sm text-zinc-400 mt-4 mb-1">
            Use <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">llmdawg.trace()</code> as
            a context manager. All LLM calls inside share the same trace ID, and you
            can attach user/session/tags scoped to just this trace.
          </p>
          <CodeBlock
            lang="python"
            code={`import llmdawg

with llmdawg.trace(
    name="rag-pipeline",
    user_id="user-42",
    tags={"feature": "search"},
) as trace_id:
    # Step 1: embed the query
    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=user_query,
    )

    # Step 2: retrieve docs (your code, not traced)
    docs = vector_db.search(embedding.data[0].embedding, top_k=5)

    # Step 3: generate answer
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_prompt(user_query, docs)},
        ],
    )

# In the dashboard: all 3 calls appear under one trace
# with a shared trace_id, user_id, and tags`}
          />
          <p className="text-xs text-zinc-600 mt-3">
            Traces nest — inner traces get their own trace ID while outer context is
            restored on exit.
          </p>
        </Section>

        {/* ── Streaming ───────────────────────────────────────────────────── */}
        <Section
          title="Streaming works out of the box"
          subtitle="Token counts, TTFT, and tool call deltas — all captured automatically"
          icon={<Layers className="w-4 h-4 text-lime-500 flex-shrink-0" />}
          defaultOpen={false}
        >
          <p className="text-sm text-zinc-400 mt-4 mb-1">
            No extra setup needed. The SDK automatically injects{" "}
            <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">stream_options.include_usage</code> so
            you get accurate token counts even on streaming calls.
          </p>
          <CodeBlock
            lang="python"
            code={`# Streaming — just use it normally
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write a poem"}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")

# When the stream ends, LLMDawg captures:
#   - Time to first token (TTFT)
#   - Total input & output tokens
#   - Prompt cache hits
#   - Full accumulated response
#   - Tool call deltas (if any)`}
          />
        </Section>

        {/* ── Tool calls ──────────────────────────────────────────────────── */}
        <Section
          title="Tool / function calls are captured in full"
          subtitle="See what tools the model called, with what arguments, in the trace viewer"
          icon={<Code2 className="w-4 h-4 text-lime-500 flex-shrink-0" />}
          defaultOpen={false}
        >
          <p className="text-sm text-zinc-400 mt-4 mb-1">
            When the model uses function calling or tool use, the SDK captures the
            full tool definitions from the request and the tool call results
            from the response &mdash; including function name, arguments, and ID.
          </p>
          <CodeBlock
            lang="python"
            code={`tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            },
        },
    }
]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What's the weather in NYC?"}],
    tools=tools,
)

# LLMDawg captures:
#   request.tools → full tool definitions
#   response.tool_calls → [{id, name, arguments}]
# Visible in the Traces detail view`}
          />
        </Section>

        {/* ── Flush on exit ───────────────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-3">
            <Terminal className="w-4 h-4 text-zinc-500" />
            <p className="text-sm font-semibold text-white">Production tip: graceful shutdown</p>
          </div>
          <p className="text-sm text-zinc-400 mb-3">
            The SDK flushes automatically via <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">atexit</code>,
            but for long-running servers you may want to flush explicitly on shutdown:
          </p>
          <CodeBlock
            lang="python"
            code={`# FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    yield
    llmdawg.flush(timeout=10)

app = FastAPI(lifespan=lifespan)

# Django — in settings.py or a signal handler
import atexit
import llmdawg
atexit.register(llmdawg.flush)`}
          />
        </div>

        {/* ── What gets captured ──────────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <Code2 className="w-4 h-4 text-zinc-500" />
            <p className="text-sm font-semibold text-white">Full capture reference</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left py-2 pr-4 text-xs font-semibold text-zinc-500 uppercase">Field</th>
                  <th className="text-left py-2 pr-4 text-xs font-semibold text-zinc-500 uppercase">Source</th>
                  <th className="text-left py-2 text-xs font-semibold text-zinc-500 uppercase">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {[
                  ["Prompt (messages)", "Auto", "Full messages array including system prompt"],
                  ["Response content", "Auto", "Text + tool calls + refusals"],
                  ["Input / output tokens", "Auto", "From usage object; streaming included"],
                  ["Cached tokens", "Auto", "OpenAI prompt_tokens_details + Anthropic cache_read"],
                  ["Cost (USD)", "Auto", "Computed server-side from token counts"],
                  ["Latency (ms)", "Auto", "Client-side measurement, not proxy-inflated"],
                  ["Time to first token", "Auto", "Streaming calls only"],
                  ["Model & provider", "Auto", "Actual model returned, not just requested"],
                  ["Tool definitions", "Auto", "Full tools/functions array from request"],
                  ["Tool call results", "Auto", "Function name, arguments, and ID"],
                  ["Request parameters", "Auto", "temperature, top_p, seed, response_format, etc."],
                  ["Error type & message", "Auto", "Exception class + message on failure"],
                  ["Embeddings", "Auto", "Model, token count, dimensions, vector count"],
                  ["User ID", "You set it", "llmdawg.set_user() or trace(user_id=...)"],
                  ["Session ID", "You set it", "llmdawg.set_session() or trace(session_id=...)"],
                  ["Tags", "You set it", "llmdawg.set_tags() or trace(tags=...)"],
                  ["Trace ID", "You set it", "llmdawg.trace() groups calls together"],
                ].map(([field, source, notes]) => (
                  <tr key={field}>
                    <td className="py-2.5 pr-4 text-zinc-300 font-medium font-mono text-xs">{field}</td>
                    <td className="py-2.5 pr-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
                          source === "Auto"
                            ? "bg-lime-500/10 text-lime-400 border-lime-500/20"
                            : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                        }`}
                      >
                        {source}
                      </span>
                    </td>
                    <td className="py-2.5 text-zinc-500 text-xs">{notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}
