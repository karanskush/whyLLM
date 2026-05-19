import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";

import { MarketingNav } from "@/components/marketing/nav";
import { MarketingFooter } from "@/components/marketing/footer";
import { CaptureExplorer } from "@/components/marketing/capture-explorer";

export const metadata: Metadata = {
  title: "What we show — whyllm",
  description:
    "Every detail whyllm captures from each LLM call — 49 indexed fields across 9 categories, aligned with the OpenTelemetry GenAI semantic conventions — plus the feature tour, the premium AI copilots it unlocks, and a plan-by-plan comparison.",
};

// ─────────────────────────────────────────────────────────────────────────────
// Standards mapping — whyllm fields ↔ OpenTelemetry GenAI semantic conventions
// ─────────────────────────────────────────────────────────────────────────────
const OTEL_MAP: { ours: string; otel: string }[] = [
  { ours: "model", otel: "gen_ai.request.model" },
  { ours: "input_tokens", otel: "gen_ai.usage.input_tokens" },
  { ours: "finish_reason", otel: "gen_ai.response.finish_reasons" },
  { ours: "provider", otel: "gen_ai.provider.name" },
];

const PROVIDERS = [
  "OpenAI",
  "Azure OpenAI",
  "Anthropic",
  "AWS Bedrock",
  "Google Vertex AI",
  "Mistral",
  "any OpenAI-compatible endpoint",
];

// ─────────────────────────────────────────────────────────────────────────────
// Feature tour
// ─────────────────────────────────────────────────────────────────────────────
type Feature = {
  tag: string;
  title: string;
  problem: string;
  body: string;
  points: string[];
  color: string;
  visual: ReactNode;
};

const FEATURES: Feature[] = [
  {
    tag: "Tracing",
    title: "Full-stack tracing",
    problem: "You can’t debug a call you never saw.",
    body: "Every LLM call becomes a searchable span, and multi-step agent calls are stitched into one trace. Filter by model, environment, user, or tag and land on the exact request in two clicks.",
    points: [
      "Raw request and response bodies, kept verbatim",
      "Agent chains reconstructed via trace_id and parent_span_id",
      "Full-text search across your entire history",
    ],
    color: "#84CC16",
    visual: (
      <div className="rounded-xl border border-white/10 bg-zinc-950 p-4">
        <div className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider mb-3">
          trace · 3 spans
        </div>
        <div className="space-y-1.5">
          {[
            { m: "gpt-4o", c: "$0.0042", l: "1.8s", ok: true },
            { m: "text-embedding-3-large", c: "$0.0001", l: "0.1s", ok: true },
            { m: "claude-sonnet-4-6", c: "$0.0091", l: "2.2s", ok: false },
          ].map((r) => (
            <div
              key={r.m}
              className="grid grid-cols-[1fr_auto_auto_auto] gap-3 items-center text-[11px] font-mono px-2.5 py-2 rounded-lg bg-white/[0.02] border border-white/[0.05]"
            >
              <span className="text-zinc-300 truncate">{r.m}</span>
              <span className="text-lime-400">{r.c}</span>
              <span className="text-zinc-500">{r.l}</span>
              <span className={r.ok ? "text-emerald-400" : "text-amber-400"}>
                {r.ok ? "✓" : "⚠"}
              </span>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    tag: "Cost",
    title: "Cost control & budgets",
    problem: "The invoice should never be the first you hear of it.",
    body: "Not just charts — enforcement. Set budgets per project, key, or user; the proxy returns HTTP 429 before an over-budget call ever reaches the provider. Auto-route to a cheaper model when a threshold trips.",
    points: [
      "Hard budget caps enforced inline, at the proxy",
      "Spend attributed by feature, user, model, or tag",
      "Auto-routing to a cheaper model on threshold",
    ],
    color: "#60A5FA",
    visual: (
      <div className="rounded-xl border border-white/10 bg-zinc-950 p-4">
        <div className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider mb-2">
          monthly budget
        </div>
        <div className="text-lg font-bold text-white mb-2">
          $127.40 <span className="text-zinc-600 text-sm">/ $300.00</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden mb-3">
          <div className="h-full w-[42%] bg-sky-400 rounded-full" />
        </div>
        <div className="inline-flex items-center gap-2 text-[11px] font-mono px-2.5 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
          HTTP 429 · budget cap enforced
        </div>
      </div>
    ),
  },
  {
    tag: "Quality",
    title: "Hallucination detection",
    problem: "Right now you find out from a screenshot on Twitter.",
    body: "A heuristic scorer runs on every response in under a millisecond — hedge ratio, repetition, overconfidence, length anomalies. An LLM judge samples only the flagged spans, so cost stays near zero.",
    points: [
      "A 0–1 confidence score on 100% of responses",
      "Heuristic flags pinpoint why a response looks off",
      "LLM-as-judge confirmation on flagged spans only",
    ],
    color: "#C084FC",
    visual: (
      <div className="rounded-xl border border-white/10 bg-zinc-950 p-4">
        <div className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider mb-2">
          hallucination score
        </div>
        <div className="text-4xl font-black text-violet-300 leading-none mb-3">0.18</div>
        <div className="flex flex-wrap gap-1.5">
          {["token_repetition", "hedge_mismatch"].map((f) => (
            <span
              key={f}
              className="text-[10px] font-mono px-2 py-1 rounded-md bg-violet-500/10 border border-violet-500/20 text-violet-300"
            >
              {f}
            </span>
          ))}
        </div>
      </div>
    ),
  },
  {
    tag: "Prediction",
    title: "Prediction & control plane",
    problem: "By the time it is an incident, it is already too late.",
    body: "Because whyllm sits inline as a proxy, every prediction can become an in-request action. Cost forecasts, rate-limit ETAs, and model-drift alerts surface on a schedule — before they turn into outages.",
    points: [
      "Month-end spend projected from week-over-week burn",
      "Rate-limit ETA — know the ceiling before you hit it",
      "Model drift caught against a rolling 7-day baseline",
    ],
    color: "#FB923C",
    visual: (
      <div className="rounded-xl border border-white/10 bg-zinc-950 p-4 space-y-2.5">
        <div className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider">
          insight · cost forecast
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-400" />
          <span className="text-sm font-semibold text-white">Budget overrun likely</span>
        </div>
        <div className="text-[12px] font-mono text-zinc-400">
          $420 month-to-date → <span className="text-amber-400">$612 projected by May 31</span>
        </div>
        <div className="text-[11px] font-mono text-zinc-600">
          severity: warning · confidence: 0.86
        </div>
      </div>
    ),
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// AI copilots — premium, AI-native features built on the complete record
// ─────────────────────────────────────────────────────────────────────────────
type Copilot = {
  name: string;
  body: string;
  tier: "Pro" | "Enterprise";
  status: "Beta" | "Roadmap";
  runsOn: string;
  icon: ReactNode;
};

const AI_COPILOTS: Copilot[] = [
  {
    name: "Ask your traces",
    body: "Search your whole history in plain English. “Which prompts regressed after the gpt-4o snapshot bump?” returns an answer grounded in real spans — every one cited and clickable.",
    tier: "Pro",
    status: "Roadmap",
    runsOn: "request.messages · response · tags",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <circle cx="7.5" cy="7.5" r="4.8" />
        <line x1="11" y1="11" x2="15.5" y2="15.5" />
      </svg>
    ),
  },
  {
    name: "Root-cause copilot",
    body: "When drift or a cost spike fires, an agent walks the surrounding spans and writes the post-mortem: what changed, which calls were hit, and the likely fix.",
    tier: "Pro",
    status: "Roadmap",
    runsOn: "trace_id · model_drift · system_fingerprint",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <circle cx="4.5" cy="4.5" r="2.2" />
        <circle cx="4.5" cy="13.5" r="2.2" />
        <circle cx="13.5" cy="9" r="2.2" />
        <path d="M6.4 5.6l5.2 2.6M6.4 12.4l5.2-2.6" />
      </svg>
    ),
  },
  {
    name: "LLM-judge evaluations",
    body: "A model judge re-scores responses for faithfulness, correctness and tone — running only on heuristically-flagged spans, so the bill stays near zero.",
    tier: "Pro",
    status: "Beta",
    runsOn: "hallucination_flags · response",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 2l5.5 1.8v4.4c0 3.7-2.6 5.6-5.5 6.8-2.9-1.2-5.5-3.1-5.5-6.8V3.8L9 2z" />
        <polyline points="6.6,8.6 8.3,10.3 11.6,6.9" />
      </svg>
    ),
  },
  {
    name: "Semantic failure clustering",
    body: "Refusals, errors and hallucinations grouped by meaning, not string match — 200 broken rows collapse into the five bugs actually behind them.",
    tier: "Pro",
    status: "Roadmap",
    runsOn: "refusal · error_type · response",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" stroke="none">
        <circle cx="5" cy="5.5" r="1.5" />
        <circle cx="8.2" cy="3.6" r="1.5" />
        <circle cx="6.4" cy="9" r="1.5" />
        <circle cx="12.8" cy="12.6" r="1.5" />
        <circle cx="10.6" cy="14.8" r="1.5" />
        <circle cx="14.6" cy="9.6" r="1.5" />
      </svg>
    ),
  },
  {
    name: "Auto-built eval suites",
    body: "Your production traffic becomes your test suite. whyllm mines real spans into a golden regression set — no manual labelling, no synthetic data.",
    tier: "Enterprise",
    status: "Roadmap",
    runsOn: "request · response · llm_judge",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3.5" y="3" width="11" height="12.5" rx="1.6" />
        <path d="M6.3 7.2l1.2 1.2 2.3-2.4M6.3 11.4l1.2 1.2 2.3-2.4" />
      </svg>
    ),
  },
  {
    name: "Prompt optimizer",
    body: "Analyses every span for an endpoint and proposes a shorter, cheaper prompt that holds quality — then A/B-tests it inline through the proxy.",
    tier: "Enterprise",
    status: "Roadmap",
    runsOn: "request.system · cost_usd · hallucination_score",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" stroke="none">
        <path d="M8 1.6l1.5 4L13.6 7l-4.1 1.4L8 12.4 6.5 8.4 2.4 7l4.1-1.4z" />
        <path d="M13.4 10.6l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7z" />
      </svg>
    ),
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Plan comparison — grouped by category
// ─────────────────────────────────────────────────────────────────────────────
const PLAN_COLUMNS: { name: string; price: string; note: string; highlight?: boolean }[] = [
  { name: "Basic", price: "$0", note: "forever" },
  { name: "Pro", price: "$10", note: "/ month", highlight: true },
  { name: "Enterprise", price: "Custom", note: "" },
];

const PLAN_GROUPS: {
  group: string;
  rows: { feature: string; values: (string | boolean)[] }[];
}[] = [
  {
    group: "Capture & history",
    rows: [
      { feature: "Calls captured", values: ["100%", "100%", "100%"] },
      { feature: "Spans / month", values: ["50,000", "Unlimited", "Unlimited"] },
      { feature: "History retention", values: ["7 days", "90 days", "Custom"] },
      { feature: "Projects", values: ["1", "Unlimited", "Unlimited"] },
      { feature: "Raw request / response bodies", values: [true, true, true] },
    ],
  },
  {
    group: "Intelligence",
    rows: [
      { feature: "Cost & token dashboard", values: [true, true, true] },
      { feature: "Hallucination scoring", values: [false, true, true] },
      { feature: "Prediction insights", values: [false, true, true] },
      { feature: "Budget enforcement (HTTP 429)", values: [false, true, true] },
      { feature: "Alerts & webhooks", values: [false, true, true] },
    ],
  },
  {
    group: "AI copilots",
    rows: [
      { feature: "LLM-judge evaluations", values: [false, true, true] },
      { feature: "Ask your traces — natural-language search", values: [false, true, true] },
      { feature: "Root-cause copilot", values: [false, true, true] },
      { feature: "Semantic failure clustering", values: [false, true, true] },
      { feature: "Auto-built eval suites", values: [false, false, true] },
      { feature: "Prompt optimizer", values: [false, false, true] },
    ],
  },
  {
    group: "Scale & security",
    rows: [
      { feature: "SSO / SAML", values: [false, false, true] },
      { feature: "Self-hosted option", values: [false, false, true] },
      { feature: "SLA guarantee", values: [false, false, true] },
    ],
  },
  {
    group: "Support",
    rows: [{ feature: "Support", values: ["Community", "Email", "Dedicated"] }],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Small server-side helpers
// ─────────────────────────────────────────────────────────────────────────────
function PlanCell({ value, highlight }: { value: string | boolean; highlight?: boolean }) {
  return (
    <div
      className="p-3.5 flex items-center justify-center text-center"
      style={{ background: highlight ? "rgba(132,204,22,0.04)" : undefined }}
    >
      {typeof value === "boolean" ? (
        value ? (
          <span className="text-lime-400 text-base">✓</span>
        ) : (
          <span className="text-zinc-700">—</span>
        )
      ) : (
        <span className="text-sm text-zinc-300">{value}</span>
      )}
    </div>
  );
}

function FeatureRow({ feature, index }: { feature: Feature; index: number }) {
  const flip = index % 2 === 1;
  return (
    <div className="grid md:grid-cols-2 gap-8 md:gap-12 items-center">
      <div className={flip ? "md:order-2" : ""}>
        <div
          className="text-[10px] font-bold uppercase tracking-widest mb-4 w-fit px-2.5 py-1 rounded-full border"
          style={{
            color: feature.color,
            borderColor: `${feature.color}30`,
            background: `${feature.color}10`,
          }}
        >
          {feature.tag}
        </div>
        <h3 className="text-2xl font-black text-white mb-2">{feature.title}</h3>
        <p className="text-zinc-500 text-sm italic mb-4">{feature.problem}</p>
        <p className="text-zinc-400 text-sm leading-relaxed mb-5">{feature.body}</p>
        <ul className="space-y-2">
          {feature.points.map((p) => (
            <li key={p} className="flex items-start gap-2.5">
              <span
                className="font-bold mt-[1px] flex-shrink-0 text-[12px]"
                style={{ color: feature.color }}
              >
                ›
              </span>
              <span className="text-zinc-300 text-[13px] leading-relaxed">{p}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className={flip ? "md:order-1" : ""}>{feature.visual}</div>
    </div>
  );
}

function CopilotCard({ c }: { c: Copilot }) {
  const beta = c.status === "Beta";
  const pro = c.tier === "Pro";
  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 flex flex-col transition-colors duration-200 hover:border-white/[0.16]">
      <div className="flex items-start justify-between mb-4">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: "rgba(192,132,252,0.1)", color: "#C084FC" }}
        >
          {c.icon}
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={
              "text-[9px] font-bold uppercase tracking-widest px-2 py-1 rounded-md border " +
              (beta
                ? "text-lime-400 border-lime-500/30 bg-lime-500/10"
                : "text-zinc-500 border-white/10 bg-white/[0.03]")
            }
          >
            {c.status}
          </span>
          <span
            className={
              "text-[9px] font-bold uppercase tracking-widest px-2 py-1 rounded-md border " +
              (pro
                ? "text-lime-400 border-lime-500/30 bg-lime-500/10"
                : "text-sky-300 border-sky-400/30 bg-sky-400/10")
            }
          >
            {c.tier}
          </span>
        </div>
      </div>
      <h3 className="text-base font-bold text-white mb-1.5">{c.name}</h3>
      <p className="text-[13px] text-zinc-400 leading-relaxed flex-1">{c.body}</p>
      <div className="mt-4 pt-3 border-t border-white/[0.05]">
        <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-600">
          Runs on
        </span>
        <div className="font-mono text-[11px] text-zinc-500 mt-1 break-words">{c.runsOn}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────
export default function WhatWeShowPage() {
  return (
    <div className="min-h-screen overflow-x-hidden" style={{ background: "#09090B", color: "#FAFAFA" }}>
      <MarketingNav />

      {/* ── HERO ──────────────────────────────────────────────────────────── */}
      <section className="relative px-6 pt-32 pb-16 overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 rounded-full pointer-events-none"
          style={{
            width: "640px",
            height: "420px",
            background: "radial-gradient(circle, rgba(132,204,22,0.09) 0%, transparent 70%)",
          }}
        />
        <div className="relative z-10 max-w-3xl mx-auto text-center">
          <p className="text-lime-500 text-xs font-semibold uppercase tracking-widest mb-4">
            What we show
          </p>
          <h1
            className="font-black tracking-tight mb-6"
            style={{ fontSize: "clamp(2.4rem, 5.6vw, 4rem)", lineHeight: 1.06 }}
          >
            <span className="block text-white">We don’t sample.</span>
            <span className="block text-white">We don’t summarize.</span>
            <span
              className="block"
              style={{
                background: "linear-gradient(90deg, #84CC16, #a3e635)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              We keep the whole call.
            </span>
          </h1>
          <p className="text-zinc-400 text-base md:text-lg leading-relaxed max-w-xl mx-auto">
            Every request through the whyllm proxy becomes one immutable span —
            49 indexed fields across 9 categories, with the raw request and
            response bodies stored verbatim. Here is every single one.
          </p>
        </div>

        {/* Hero stats */}
        <div className="relative z-10 flex flex-wrap items-center justify-center gap-x-2 gap-y-6 mt-12">
          {[
            { v: "9", l: "capture categories" },
            { v: "49", l: "indexed fields" },
            { v: "0%", l: "sampled — we keep all of it" },
            { v: "100%", l: "captured from request #1" },
          ].map((s, i) => (
            <div key={s.l} className="flex items-center">
              {i > 0 && (
                <div className="h-8 w-px bg-gradient-to-b from-transparent via-zinc-700 to-transparent mx-2 sm:mx-4" />
              )}
              <div className="px-3 text-center">
                <div
                  className="font-black leading-none tracking-tight"
                  style={{
                    fontSize: "1.7rem",
                    color: "#84CC16",
                    textShadow: "0 0 28px rgba(132,204,22,0.4)",
                  }}
                >
                  {s.v}
                </div>
                <div className="text-[10px] text-zinc-500 mt-2 uppercase tracking-widest">
                  {s.l}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CAPTURE EXPLORER ──────────────────────────────────────────────── */}
      <section id="capture" className="px-6 py-20">
        <div className="max-w-5xl mx-auto text-center mb-12">
          <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
            Anatomy of a captured call
          </p>
          <h2 className="text-3xl md:text-4xl font-black text-white leading-tight">
            Pick a category. See every field.
          </h2>
          <p className="text-zinc-500 text-base mt-4 max-w-xl mx-auto">
            This is the real span schema — not a marketing summary. Tap any tile
            to inspect exactly what whyllm records.
          </p>
        </div>
        <CaptureExplorer />
      </section>

      {/* ── STANDARDS STRIP ───────────────────────────────────────────────── */}
      <section className="px-6 py-16 border-y border-white/[0.05]">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
            Open by default
          </p>
          <h2 className="text-2xl md:text-3xl font-black text-white leading-tight mb-4">
            Speaks the standard. No lock-in.
          </h2>
          <p className="text-zinc-400 text-sm md:text-base leading-relaxed max-w-2xl mx-auto mb-8">
            whyllm&apos;s span schema is aligned with the{" "}
            <span className="text-zinc-200">OpenTelemetry GenAI semantic conventions</span> —
            the fields map straight across, so your data stays portable. Export
            it, pipe it into any OTel backend, leave whenever you want.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2.5 mb-10">
            {OTEL_MAP.map((m) => (
              <div
                key={m.ours}
                className="flex items-center gap-2 text-[11px] font-mono px-3 py-1.5 rounded-lg bg-white/[0.02] border border-white/[0.07]"
              >
                <span className="text-zinc-300">{m.ours}</span>
                <span className="text-zinc-600">→</span>
                <span className="text-lime-400">{m.otel}</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-zinc-600 uppercase tracking-widest mb-4 font-medium">
            Captures calls to every major provider
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
            {PROVIDERS.map((p) => (
              <span key={p} className="text-sm text-zinc-500 font-semibold tracking-tight">
                {p}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── FEATURE TOUR ──────────────────────────────────────────────────── */}
      <section id="tour" className="px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              Feature tour
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-white leading-tight">
              What that data turns into
            </h2>
            <p className="text-zinc-500 text-base mt-4 max-w-xl mx-auto">
              Capture is the start. These four pillars are what whyllm does with it.
            </p>
          </div>
          <div className="space-y-16 md:space-y-20">
            {FEATURES.map((f, i) => (
              <FeatureRow key={f.title} feature={f} index={i} />
            ))}
          </div>
        </div>
      </section>

      {/* ── AI COPILOTS ───────────────────────────────────────────────────── */}
      <section id="copilots" className="px-6 py-20 border-t border-white/[0.05]">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              Premium · AI copilots
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-white leading-tight">
              AI that works because nothing was thrown away.
            </h2>
            <p className="text-zinc-500 text-base mt-4 max-w-2xl mx-auto">
              Sampled, summarised observability data can&apos;t power real AI
              features — there&apos;s nothing for a model to read. whyllm keeps
              every call verbatim, so these premium copilots reason over the
              whole record. One is in beta today; the rest are on the roadmap.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {AI_COPILOTS.map((c) => (
              <CopilotCard key={c.name} c={c} />
            ))}
          </div>

          <p className="text-center text-[12px] text-zinc-600 mt-8">
            Available on <span className="text-lime-400 font-semibold">Pro</span>{" "}
            and <span className="text-sky-300 font-semibold">Enterprise</span> —
            see the plan breakdown below.
          </p>
        </div>
      </section>

      {/* ── PLAN COMPARISON ───────────────────────────────────────────────── */}
      <section id="plans" className="px-6 py-20 border-t border-white/[0.05]">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              Plans
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-white leading-tight">
              What you get on each plan
            </h2>
            <p className="text-zinc-500 text-base mt-4 max-w-xl mx-auto">
              Same proxy, same full capture on every plan. Higher tiers unlock
              enforcement, AI copilots, and scale.
            </p>
          </div>

          <div className="rounded-2xl border border-white/[0.08] overflow-hidden">
            {/* Header row */}
            <div className="grid grid-cols-[1.7fr_1fr_1fr_1fr]">
              <div className="p-4 bg-white/[0.02] border-b border-white/[0.07]" />
              {PLAN_COLUMNS.map((col) => (
                <div
                  key={col.name}
                  className="p-4 text-center border-b border-white/[0.07]"
                  style={{
                    background: col.highlight ? "rgba(132,204,22,0.05)" : "rgba(255,255,255,0.02)",
                  }}
                >
                  <div className={`text-sm font-bold ${col.highlight ? "text-lime-400" : "text-white"}`}>
                    {col.name}
                  </div>
                  <div className="mt-1">
                    <span className="text-lg font-black text-white">{col.price}</span>
                    {col.note && (
                      <span className="block text-[10px] text-zinc-500 mt-0.5">{col.note}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Grouped feature rows */}
            {PLAN_GROUPS.map((grp) => (
              <div key={grp.group}>
                <div className="grid grid-cols-[1.7fr_1fr_1fr_1fr]">
                  <div className="col-span-4 px-4 py-2.5 bg-white/[0.03] border-b border-white/[0.05]">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                      {grp.group}
                    </span>
                  </div>
                </div>
                {grp.rows.map((row) => (
                  <div
                    key={row.feature}
                    className="grid grid-cols-[1.7fr_1fr_1fr_1fr] border-b border-white/[0.04] last:border-0"
                  >
                    <div className="p-3.5 text-sm text-zinc-300">{row.feature}</div>
                    {row.values.map((v, i) => (
                      <PlanCell key={i} value={v} highlight={PLAN_COLUMNS[i].highlight} />
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-10">
            <Link
              href="/register"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-black font-bold text-sm bg-lime-500 hover:bg-lime-400 transition-all duration-150 shadow-[0_0_24px_rgba(132,204,22,0.35)]"
            >
              Start free on Basic →
            </Link>
            <Link
              href="/landing#pricing"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-zinc-400 font-medium text-sm border border-white/10 hover:border-white/20 hover:text-white transition-all duration-150"
            >
              See full pricing
            </Link>
          </div>
        </div>
      </section>

      {/* ── FINAL CTA ─────────────────────────────────────────────────────── */}
      <section className="px-6 py-24">
        <div className="max-w-3xl mx-auto text-center">
          <div
            className="rounded-3xl border border-lime-500/20 p-12 relative overflow-hidden"
            style={{ background: "rgba(132,204,22,0.04)" }}
          >
            <div
              className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full pointer-events-none"
              style={{
                width: "400px",
                height: "200px",
                background: "radial-gradient(ellipse, rgba(132,204,22,0.15) 0%, transparent 70%)",
              }}
            />
            <div className="relative z-10">
              <h2 className="text-3xl md:text-4xl font-black text-white mb-4 leading-tight">
                Stop guessing what your LLMs did.
              </h2>
              <p className="text-zinc-400 text-base mb-9 max-w-md mx-auto">
                Repoint one base URL and the next call you make is captured
                whole — all 49 fields.
              </p>
              <Link
                href="/register"
                className="inline-flex items-center gap-2 px-8 py-4 rounded-xl text-black font-bold text-base bg-lime-500 hover:bg-lime-400 transition-all duration-150 shadow-[0_0_30px_rgba(132,204,22,0.4)]"
              >
                Start monitoring free →
              </Link>
            </div>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
