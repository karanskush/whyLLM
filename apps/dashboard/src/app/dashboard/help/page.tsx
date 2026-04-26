"use client";

import { useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { cn } from "@/lib/utils";
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

// ── Collapsible section ───────────────────────────────────────────────────────

function Section({
  title,
  subtitle,
  children,
  defaultOpen = false,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-zinc-800/50 transition-colors"
      >
        <div>
          <p className="text-sm font-semibold text-white">{title}</p>
          <p className="text-xs text-zinc-500 mt-0.5">{subtitle}</p>
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
      <Topbar title="Onboarding Guide" />

      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">

        {/* Intro */}
        <div className="bg-lime-500/10 border border-lime-500/20 rounded-xl px-6 py-5">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-lime-400" />
            <span className="text-sm font-semibold text-lime-300">
              You can be up and running in under 2 minutes.
            </span>
          </div>
          <p className="text-sm text-zinc-400">
            whyllm sits between your app and OpenAI / Anthropic. Every LLM call
            flows through us — you get full visibility into tokens, cost, latency,
            and errors without changing a single line of your application code.
          </p>
        </div>

        {/* Step 1 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={1} />
            <div>
              <p className="text-sm font-semibold text-white">Get your API key</p>
              <p className="text-xs text-zinc-500">Settings → API Keys → New Key</p>
            </div>
            <Key className="w-4 h-4 text-zinc-700 ml-auto" />
          </div>
          <p className="text-sm text-zinc-400 mb-3">
            Go to{" "}
            <a href="/dashboard/settings" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">
              Settings → API Keys
            </a>{" "}
            and click <strong className="text-zinc-200">New Key</strong>. Give it a name (e.g.{" "}
            <code className="text-xs bg-zinc-800 text-zinc-300 px-1 py-0.5 rounded">Production</code>),
            choose your environment, and copy the key immediately — it is shown only once.
          </p>
          <div className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
            <span className="text-xs text-amber-400">
              Your key looks like: <code className="font-mono font-semibold">wl-prod_xxxxxxxxxxxx</code>
            </span>
          </div>
        </div>

        {/* Step 2 — integration methods */}
        <div>
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={2} />
            <p className="text-sm font-semibold text-white">Connect your app — pick any method</p>
          </div>

          <div className="space-y-3 ml-9">

            <Section
              title="Option A — Two env vars (recommended, zero code changes)"
              subtitle="Works with any OpenAI SDK in any language. Takes 30 seconds."
              defaultOpen={true}
            >
              <p className="text-sm text-zinc-400 mt-4 mb-1">
                The OpenAI SDK reads <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">OPENAI_BASE_URL</code> natively.
                Point it at whyllm and add your project key — that's it.
              </p>
              <CodeBlock
                lang="bash"
                code={`export OPENAI_BASE_URL=http://localhost:17823/proxy/v1
export WHYLLM_API_KEY=wl-prod_your_key_here

# Then run your app exactly as before
python app.py`}
              />
              <p className="text-xs text-zinc-600 mt-2">
                whyllm forwards every request to OpenAI using your own OpenAI key
                (passed in the <code>Authorization</code> header by the SDK automatically).
              </p>
            </Section>

            <Section
              title="Option B — CLI wrapper (Python apps, zero code changes)"
              subtitle="Prefix your start command. Works with FastAPI, Django, Celery, scripts."
            >
              <p className="text-sm text-zinc-400 mt-4 mb-1">
                Install the SDK, then prefix your start command with <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">whyllm-run</code>.
                It patches the OpenAI and Anthropic clients before any of your code runs.
              </p>
              <CodeBlock
                lang="bash"
                code={`pip install whyllm

# Prefix your existing start command — nothing else changes
whyllm-run python app.py
whyllm-run uvicorn main:app --host 0.0.0.0
whyllm-run gunicorn app:app`}
              />
              <CodeBlock
                lang="bash"
                code={`# Set these env vars once
export WHYLLM_API_KEY=wl-prod_your_key_here
export WHYLLM_BASE_URL=http://localhost:17823`}
              />
            </Section>

            <Section
              title="Option C — Proxy URL in code (any language)"
              subtitle="2 lines. Works with Python, TypeScript, Go, Ruby, anything with an HTTP client."
            >
              <p className="text-sm text-zinc-400 mt-4 mb-1">Python:</p>
              <CodeBlock
                lang="python"
                code={`from openai import OpenAI

client = OpenAI(
    api_key="sk-...",                        # your own OpenAI key
    base_url="http://localhost:17823/proxy/v1",
    default_headers={"X-whyllm-Key": "wl-prod_your_key_here"},
)

# All your existing calls work unchanged
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)`}
              />
              <p className="text-sm text-zinc-400 mt-4 mb-1">TypeScript / Node.js:</p>
              <CodeBlock
                lang="typescript"
                code={`import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  baseURL: "http://localhost:17823/proxy/v1",
  defaultHeaders: { "X-whyllm-Key": "wl-prod_your_key_here" },
});`}
              />
              <p className="text-sm text-zinc-400 mt-4 mb-1">Anthropic (Python):</p>
              <CodeBlock
                lang="python"
                code={`import anthropic

client = anthropic.Anthropic(
    api_key="sk-ant-...",                         # your own Anthropic key
    base_url="http://localhost:17823/proxy",
    default_headers={"X-whyllm-Key": "wl-prod_your_key_here"},
)`}
              />
            </Section>

            <Section
              title="Option D — OpenTelemetry (enterprise)"
              subtitle="Already on OTel? Change one endpoint. No SDK swap needed."
            >
              <p className="text-sm text-zinc-400 mt-4 mb-1">
                If your stack already emits OpenTelemetry spans (Traceloop, OpenLLMetry,
                LangChain, etc.), just redirect the OTLP exporter to whyllm:
              </p>
              <CodeBlock
                lang="bash"
                code={`export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:17823/otlp
export OTEL_EXPORTER_OTLP_HEADERS="X-whyllm-Key=wl-prod_your_key_here"`}
              />
              <p className="text-xs text-zinc-600 mt-2">
                whyllm parses OpenAI and Anthropic semantic conventions from your existing
                spans. No new instrumentation required.
              </p>
            </Section>
          </div>
        </div>

        {/* Step 3 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={3} />
            <div>
              <p className="text-sm font-semibold text-white">Make a test call and verify</p>
              <p className="text-xs text-zinc-500">Takes about 10 seconds</p>
            </div>
            <Terminal className="w-4 h-4 text-zinc-700 ml-auto" />
          </div>
          <p className="text-sm text-zinc-400 mb-3">
            Make any LLM call from your app. Then open{" "}
            <a href="/dashboard/traces" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">
              Traces
            </a>{" "}
            — your call should appear within 1–2 seconds.
          </p>
          <CodeBlock
            lang="python"
            code={`# Quick sanity check — run this once after connecting
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url="http://localhost:17823/proxy/v1",
    default_headers={"X-whyllm-Key": os.environ["WHYLLM_API_KEY"]},
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say hello in one word"}],
)
print(resp.choices[0].message.content)
# → Now check the Traces tab in whyllm`}
          />
        </div>

        {/* Step 4 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={4} />
            <div>
              <p className="text-sm font-semibold text-white">Set a budget (optional but recommended)</p>
              <p className="text-xs text-zinc-500">Prevent runaway spend with a hard stop</p>
            </div>
          </div>
          <p className="text-sm text-zinc-400 mb-3">
            Go to{" "}
            <a href="/dashboard/settings" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">
              Settings → Budgets
            </a>{" "}
            and create a daily budget. When your project hits the limit, whyllm
            returns <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">HTTP 429</code> instead
            of forwarding the request — no surprise bills.
          </p>
          <div className="grid grid-cols-3 gap-3 mt-4">
            {[
              { label: "Daily", desc: "Resets at midnight UTC" },
              { label: "Alert only", desc: "Notify but don't block" },
              { label: "Hard stop", desc: "Block requests when hit" },
            ].map(({ label, desc }) => (
              <div key={label} className="rounded-lg border border-zinc-800 bg-zinc-800/30 px-3 py-2 text-center">
                <p className="text-xs font-semibold text-zinc-200">{label}</p>
                <p className="text-xs text-zinc-500 mt-0.5">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Done */}
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-6 py-5 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-emerald-300">You're all set.</p>
            <p className="text-sm text-zinc-400 mt-1">
              Every LLM call your app makes will now appear in{" "}
              <a href="/dashboard/traces" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">Traces</a>,
              costs will roll up in{" "}
              <a href="/dashboard/cost" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">Cost</a>,
              and the{" "}
              <a href="/dashboard" className="text-lime-400 hover:text-lime-300 font-medium transition-colors">Overview</a>{" "}
              dashboard shows live activity.
            </p>
          </div>
        </div>

        {/* Quick reference */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <Code2 className="w-4 h-4 text-zinc-500" />
            <p className="text-sm font-semibold text-white">Quick reference</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left py-2 pr-4 text-xs font-semibold text-zinc-500 uppercase">Method</th>
                  <th className="text-left py-2 pr-4 text-xs font-semibold text-zinc-500 uppercase">Code changes</th>
                  <th className="text-left py-2 text-xs font-semibold text-zinc-500 uppercase">Time to first trace</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {[
                  ["Env vars (Option A)", "0 lines", "< 30 seconds"],
                  ["CLI wrapper (Option B)", "0 lines", "< 2 minutes"],
                  ["Proxy URL in code (Option C)", "2 lines", "< 5 minutes"],
                  ["OpenTelemetry (Option D)", "0 lines", "< 2 minutes"],
                ].map(([method, code, time]) => (
                  <tr key={method}>
                    <td className="py-2.5 pr-4 text-zinc-300 font-medium">{method}</td>
                    <td className="py-2.5 pr-4">
                      <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-medium">
                        {code}
                      </span>
                    </td>
                    <td className="py-2.5 text-zinc-500">{time}</td>
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
