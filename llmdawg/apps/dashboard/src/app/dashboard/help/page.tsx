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
  Globe,
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
      className="absolute top-2 right-2 p-1.5 rounded bg-gray-700 hover:bg-gray-600 transition-colors"
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-emerald-400" />
      ) : (
        <Copy className="w-3.5 h-3.5 text-gray-300" />
      )}
    </button>
  );
}

// ── Code block ────────────────────────────────────────────────────────────────

function CodeBlock({ code, lang = "bash" }: { code: string; lang?: string }) {
  return (
    <div className="relative mt-3 rounded-lg bg-gray-900 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-700">
        <span className="text-xs text-gray-500 font-mono">{lang}</span>
      </div>
      <pre className="px-4 py-3 overflow-x-auto text-sm text-gray-200 whitespace-pre">
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
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div>
          <p className="text-sm font-semibold text-gray-900">{title}</p>
          <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
        </div>
        {open ? (
          <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
        )}
      </button>
      {open && <div className="px-6 pb-6 border-t border-gray-100">{children}</div>}
    </div>
  );
}

// ── Step badge ────────────────────────────────────────────────────────────────

function StepBadge({ n }: { n: number }) {
  return (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex-shrink-0">
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
        <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-6 py-5">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-indigo-600" />
            <span className="text-sm font-semibold text-indigo-900">
              You can be up and running in under 2 minutes.
            </span>
          </div>
          <p className="text-sm text-indigo-800">
            WhyLLM sits between your app and OpenAI / Anthropic. Every LLM call
            flows through us — you get full visibility into tokens, cost, latency,
            and errors without changing a single line of your application code.
          </p>
        </div>

        {/* Step 1 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={1} />
            <div>
              <p className="text-sm font-semibold text-gray-900">Get your API key</p>
              <p className="text-xs text-gray-500">Settings → API Keys → New Key</p>
            </div>
            <Key className="w-4 h-4 text-gray-300 ml-auto" />
          </div>
          <p className="text-sm text-gray-600 mb-3">
            Go to{" "}
            <a href="/dashboard/settings" className="text-indigo-600 hover:underline font-medium">
              Settings → API Keys
            </a>{" "}
            and click <strong>New Key</strong>. Give it a name (e.g.{" "}
            <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">Production</code>),
            choose your environment, and copy the key immediately — it is shown only once.
          </p>
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            <span className="text-xs text-amber-800">
              Your key looks like: <code className="font-mono font-semibold">ld-prod_xxxxxxxxxxxx</code>
            </span>
          </div>
        </div>

        {/* Step 2 — integration methods */}
        <div>
          <div className="flex items-center gap-3 mb-3">
            <StepBadge n={2} />
            <p className="text-sm font-semibold text-gray-900">Connect your app — pick any method</p>
          </div>

          <div className="space-y-3 ml-9">

            {/* Level 0a */}
            <Section
              title="Option A — Two env vars (recommended, zero code changes)"
              subtitle="Works with any OpenAI SDK in any language. Takes 30 seconds."
              defaultOpen={true}
            >
              <p className="text-sm text-gray-600 mt-4 mb-1">
                The OpenAI SDK reads <code className="text-xs bg-gray-100 px-1 rounded">OPENAI_BASE_URL</code> natively.
                Point it at WhyLLM and add your project key — that's it.
              </p>
              <CodeBlock
                lang="bash"
                code={`export OPENAI_BASE_URL=http://localhost:17823/openai
export WHYLLM_API_KEY=ld-prod_your_key_here

# Then run your app exactly as before
python app.py`}
              />
              <p className="text-xs text-gray-400 mt-2">
                WhyLLM forwards every request to OpenAI using your own OpenAI key
                (passed in the <code>Authorization</code> header by the SDK automatically).
              </p>
            </Section>

            {/* Level 0b */}
            <Section
              title="Option B — CLI wrapper (Python apps, zero code changes)"
              subtitle="Prefix your start command. Works with FastAPI, Django, Celery, scripts."
            >
              <p className="text-sm text-gray-600 mt-4 mb-1">
                Install the SDK, then prefix your start command with <code className="text-xs bg-gray-100 px-1 rounded">whyllm-run</code>.
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
export WHYLLM_API_KEY=ld-prod_your_key_here
export WHYLLM_BASE_URL=http://localhost:17823`}
              />
            </Section>

            {/* Level 2 */}
            <Section
              title="Option C — Proxy URL in code (any language)"
              subtitle="2 lines. Works with Python, TypeScript, Go, Ruby, anything with an HTTP client."
            >
              <p className="text-sm text-gray-600 mt-4 mb-1">Python:</p>
              <CodeBlock
                lang="python"
                code={`from openai import OpenAI

client = OpenAI(
    api_key="sk-...",                        # your own OpenAI key
    base_url="http://localhost:17823/openai",
    default_headers={"X-WhyLLM-Key": "ld-prod_your_key_here"},
)

# All your existing calls work unchanged
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)`}
              />
              <p className="text-sm text-gray-600 mt-4 mb-1">TypeScript / Node.js:</p>
              <CodeBlock
                lang="typescript"
                code={`import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  baseURL: "http://localhost:17823/openai",
  defaultHeaders: { "X-WhyLLM-Key": "ld-prod_your_key_here" },
});`}
              />
              <p className="text-sm text-gray-600 mt-4 mb-1">Anthropic (Python):</p>
              <CodeBlock
                lang="python"
                code={`import anthropic

client = anthropic.Anthropic(
    api_key="sk-ant-...",                         # your own Anthropic key
    base_url="http://localhost:17823/anthropic",
    default_headers={"X-WhyLLM-Key": "ld-prod_your_key_here"},
)`}
              />
            </Section>

            {/* OTel */}
            <Section
              title="Option D — OpenTelemetry (enterprise)"
              subtitle="Already on OTel? Change one endpoint. No SDK swap needed."
            >
              <p className="text-sm text-gray-600 mt-4 mb-1">
                If your stack already emits OpenTelemetry spans (Traceloop, OpenLLMetry,
                LangChain, etc.), just redirect the OTLP exporter to WhyLLM:
              </p>
              <CodeBlock
                lang="bash"
                code={`export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:17823/otlp
export OTEL_EXPORTER_OTLP_HEADERS="X-WhyLLM-Key=ld-prod_your_key_here"`}
              />
              <p className="text-xs text-gray-400 mt-2">
                WhyLLM parses OpenAI and Anthropic semantic conventions from your existing
                spans. No new instrumentation required.
              </p>
            </Section>
          </div>
        </div>

        {/* Step 3 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={3} />
            <div>
              <p className="text-sm font-semibold text-gray-900">Make a test call and verify</p>
              <p className="text-xs text-gray-500">Takes about 10 seconds</p>
            </div>
            <Terminal className="w-4 h-4 text-gray-300 ml-auto" />
          </div>
          <p className="text-sm text-gray-600 mb-3">
            Make any LLM call from your app. Then open{" "}
            <a href="/dashboard/traces" className="text-indigo-600 hover:underline font-medium">
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
    base_url="http://localhost:17823/openai",
    default_headers={"X-WhyLLM-Key": os.environ["WHYLLM_API_KEY"]},
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say hello in one word"}],
)
print(resp.choices[0].message.content)
# → Now check the Traces tab in WhyLLM`}
          />
        </div>

        {/* Step 4 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <StepBadge n={4} />
            <div>
              <p className="text-sm font-semibold text-gray-900">Set a budget (optional but recommended)</p>
              <p className="text-xs text-gray-500">Prevent runaway spend with a hard stop</p>
            </div>
          </div>
          <p className="text-sm text-gray-600 mb-3">
            Go to{" "}
            <a href="/dashboard/settings" className="text-indigo-600 hover:underline font-medium">
              Settings → Budgets
            </a>{" "}
            and create a daily budget. When your project hits the limit, WhyLLM
            returns <code className="text-xs bg-gray-100 px-1 rounded">HTTP 429</code> instead
            of forwarding the request — no surprise bills.
          </p>
          <div className="grid grid-cols-3 gap-3 mt-4">
            {[
              { label: "Daily", desc: "Resets at midnight UTC" },
              { label: "Alert only", desc: "Notify but don't block" },
              { label: "Hard stop", desc: "Block requests when hit" },
            ].map(({ label, desc }) => (
              <div key={label} className="rounded-lg border border-gray-200 px-3 py-2 text-center">
                <p className="text-xs font-semibold text-gray-800">{label}</p>
                <p className="text-xs text-gray-400 mt-0.5">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Done */}
        <div className="bg-emerald-50 border border-emerald-100 rounded-xl px-6 py-5 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-emerald-900">You're all set.</p>
            <p className="text-sm text-emerald-800 mt-1">
              Every LLM call your app makes will now appear in{" "}
              <a href="/dashboard/traces" className="font-medium underline">Traces</a>,
              costs will roll up in{" "}
              <a href="/dashboard/cost" className="font-medium underline">Cost</a>,
              and the{" "}
              <a href="/dashboard" className="font-medium underline">Overview</a>{" "}
              dashboard shows live activity.
            </p>
          </div>
        </div>

        {/* Quick reference */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-2 mb-4">
            <Code2 className="w-4 h-4 text-gray-400" />
            <p className="text-sm font-semibold text-gray-900">Quick reference</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2 pr-4 text-xs font-semibold text-gray-500 uppercase">Method</th>
                  <th className="text-left py-2 pr-4 text-xs font-semibold text-gray-500 uppercase">Code changes</th>
                  <th className="text-left py-2 text-xs font-semibold text-gray-500 uppercase">Time to first trace</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {[
                  ["Env vars (Option A)", "0 lines", "< 30 seconds"],
                  ["CLI wrapper (Option B)", "0 lines", "< 2 minutes"],
                  ["Proxy URL in code (Option C)", "2 lines", "< 5 minutes"],
                  ["OpenTelemetry (Option D)", "0 lines", "< 2 minutes"],
                ].map(([method, code, time]) => (
                  <tr key={method}>
                    <td className="py-2.5 pr-4 text-gray-800 font-medium">{method}</td>
                    <td className="py-2.5 pr-4">
                      <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-xs font-medium">
                        {code}
                      </span>
                    </td>
                    <td className="py-2.5 text-gray-500">{time}</td>
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
