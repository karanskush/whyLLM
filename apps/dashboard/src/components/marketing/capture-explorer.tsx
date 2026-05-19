"use client";

import { useState } from "react";

// ─────────────────────────────────────────────────────────────────────────────
// Capture explorer — interactive "anatomy of a captured call"
//
// Every request through the whyllm proxy becomes one immutable span. The data
// below is the real span schema: 9 categories, 49 indexed fields. Picking a
// category tile drives the inspector panel underneath.
// ─────────────────────────────────────────────────────────────────────────────

type Field = { key: string; example: string; note: string };
type Category = {
  id: string;
  label: string;
  blurb: string;
  color: string;
  fields: Field[];
};

const CATEGORIES: Category[] = [
  {
    id: "request",
    label: "Request",
    blurb: "Exactly as it left your app — nothing reconstructed.",
    color: "#84CC16",
    fields: [
      { key: "provider", example: '"openai"', note: "Upstream the call was routed to" },
      { key: "model", example: '"gpt-4o"', note: "Requested model, canonicalized across dated snapshots" },
      { key: "request.messages", example: "[ {role, content}, … ]", note: "The full message array, stored verbatim" },
      { key: "request.system", example: '"You are…"  +  sha256', note: "System prompt kept separate, hashed for version tracking" },
      { key: "request.temperature", example: "0.7", note: "Sampling parameters exactly as sent" },
      { key: "request.max_tokens", example: "1024", note: "Generation ceiling requested" },
      { key: "request.tools", example: "[ {name, schema}, … ]", note: "Tool / function definitions offered to the model" },
      { key: "request.stream", example: "true", note: "Whether the response was streamed" },
      { key: "headers", example: "user-agent · sdk_version · …", note: "Request headers, including custom X-whyllm-Tag-*" },
    ],
  },
  {
    id: "response",
    label: "Response",
    blurb: "The whole completion — never truncated, never summarized.",
    color: "#84CC16",
    fields: [
      { key: "response…message.content", example: '"The capital of France is…"', note: "The completion text, in full" },
      { key: "finish_reason", example: '"stop" | "tool_calls" | "length"', note: "Why the model stopped generating" },
      { key: "response.tool_calls", example: "[ {name, arguments} ]", note: "Functions the model chose to call" },
      { key: "system_fingerprint", example: '"fp_44709d6fcb"', note: "Model build id — a drift signal" },
      { key: "response  (raw)", example: "{ … entire provider body … }", note: "Stored verbatim so any call can be audited later" },
      { key: "refusal", example: 'null | "I can’t help with…"', note: "Captured when the model declines to answer" },
    ],
  },
  {
    id: "tokens",
    label: "Tokens",
    blurb: "Every token class the provider reports, counted apart.",
    color: "#60A5FA",
    fields: [
      { key: "input_tokens", example: "1,204", note: "Prompt tokens consumed" },
      { key: "output_tokens", example: "312", note: "Completion tokens generated" },
      { key: "cached_tokens", example: "896", note: "Prompt-cache reads — billed at the lower rate" },
      { key: "reasoning_tokens", example: "0", note: "Hidden reasoning tokens on o-series models" },
      { key: "total_tokens", example: "1,516", note: "Generated column — always internally consistent" },
    ],
  },
  {
    id: "cost",
    label: "Cost",
    blurb: "Exact USD from live rate cards — Decimal math, no float drift.",
    color: "#60A5FA",
    fields: [
      { key: "cost_usd", example: "$0.004210", note: "Exact cost of this single call" },
      { key: "input / output / cached", example: "priced per-1K separately", note: "Each token class billed at its own rate" },
      { key: "rate_card", example: "gpt-4o · $2.50 / $10.00 per 1M", note: "The pricing snapshot applied to this call" },
      { key: "cumulative", example: "$127.40 month-to-date", note: "Rolled up by project, key, user, or tag" },
      { key: "unit_cost", example: "$0.0034 / call", note: "Averages computed for cost attribution" },
    ],
  },
  {
    id: "performance",
    label: "Performance",
    blurb: "Measured, not estimated — including the overhead we add.",
    color: "#60A5FA",
    fields: [
      { key: "latency_ms", example: "1,840", note: "Total wall-clock, request to last byte" },
      { key: "ttft_ms", example: "612", note: "Time to first token" },
      { key: "proxy_overhead_ms", example: "7", note: "Overhead whyllm itself added — measured honestly" },
      { key: "timings", example: "{ connect, generation, … }", note: "Per-phase latency breakdown" },
      { key: "started_at / ended_at", example: "2026-05-19T09:14:02Z", note: "Exact call boundaries, to the microsecond" },
    ],
  },
  {
    id: "quality",
    label: "Quality & safety",
    blurb: "A confidence read on every response — in under a millisecond.",
    color: "#C084FC",
    fields: [
      { key: "hallucination_score", example: "0.18", note: "0–1 heuristic score, computed on every call" },
      { key: "hallucination_flags", example: "{ overconfident_language: 0.4 }", note: "Which heuristics fired: repetition, hedging, overconfidence, length" },
      { key: "llm_judge", example: "sampled · flagged spans only", note: "A model judge re-checks only the flagged calls — cost stays near zero" },
      { key: "status_signals", example: "refusal · empty · malformed", note: "Degenerate responses caught and labelled" },
    ],
  },
  {
    id: "reliability",
    label: "Reliability",
    blurb: "What went wrong — and how close you are to the next limit.",
    color: "#FB923C",
    fields: [
      { key: "status", example: '"success" | "error" | "timeout"', note: "Outcome of the call" },
      { key: "error_type / error_message", example: '"RateLimitError" · "429 …"', note: "Classified failure detail" },
      { key: "rate_limit_limit_*", example: "requests & tokens ceilings", note: "The provider ceiling — not just what is remaining" },
      { key: "rate_limit_remaining / reset", example: "4,210  ·  resets in 18s", note: "Live headroom and when it refills" },
      { key: "retries / fallbacks", example: "1 retry → ok", note: "Recovery actions taken on the call" },
    ],
  },
  {
    id: "lineage",
    label: "Lineage & attribution",
    blurb: "Every call placed in context — who, what, which chain.",
    color: "#FB923C",
    fields: [
      { key: "trace_id / parent_span_id", example: "uuid · uuid", note: "Multi-step agent chains stitched into one trace" },
      { key: "user_id / session_id", example: '"u_8821" · "s_5f0a"', note: "Tie spend and quality back to real users" },
      { key: "environment", example: '"production"', note: "Keep prod separate from staging noise" },
      { key: "tags", example: '{ feature: "summarize" }', note: "Arbitrary dimensions you attach per call" },
      { key: "name / kind", example: '"POST /v1/chat" · "llm_call"', note: "Auto-derived endpoint name and span kind" },
      { key: "source / sdk_version", example: '"proxy" · "1.4.0"', note: "How the span reached whyllm" },
    ],
  },
  {
    id: "predictions",
    label: "Predictions",
    blurb: "Forward-looking — computed before it becomes an incident.",
    color: "#84CC16",
    fields: [
      { key: "cost_forecast", example: '"$420 → $612 by May 31"', note: "Month-to-date spend projected to month-end + week-over-week acceleration" },
      { key: "rate_limit_eta", example: '"ceiling in ~6h"', note: "When you will hit the provider limit at the current burn rate" },
      { key: "model_drift", example: '"latency +38% vs 7-day"', note: "24h window vs lagged 7-day baseline on latency, errors, quality" },
      { key: "insight metadata", example: "severity · confidence · predicted_for", note: "Every prediction is itself a tracked, resolvable record" },
    ],
  },
];

export function CaptureExplorer() {
  const [active, setActive] = useState(0);
  const cat = CATEGORIES[active];

  return (
    <div className="max-w-5xl mx-auto">
      {/* Category tiles — a bento grid that doubles as the selector */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {CATEGORIES.map((c, i) => {
          const on = i === active;
          return (
            <button
              key={c.id}
              onClick={() => setActive(i)}
              className="text-left rounded-xl border p-4 transition-all duration-200 cursor-pointer"
              style={{
                background: on ? `${c.color}12` : "rgba(255,255,255,0.02)",
                borderColor: on ? `${c.color}55` : "rgba(255,255,255,0.07)",
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <span
                  className="w-1.5 h-1.5 rounded-full transition-colors duration-200"
                  style={{ background: on ? c.color : "#3f3f46" }}
                />
                <span className="text-[10px] font-mono text-zinc-600">
                  {c.fields.length} fields
                </span>
              </div>
              <div
                className="text-sm font-bold transition-colors duration-200"
                style={{ color: on ? c.color : "#fafafa" }}
              >
                {c.label}
              </div>
              <div className="text-[11px] text-zinc-500 leading-snug mt-1">{c.blurb}</div>
            </button>
          );
        })}
      </div>

      {/* Inspector panel — the selected category's real fields */}
      <div className="mt-4 rounded-2xl border border-white/10 bg-zinc-950 overflow-hidden shadow-[0_24px_80px_rgba(0,0,0,0.5)]">
        <div className="flex items-center gap-2 px-4 py-3 bg-white/[0.02] border-b border-white/[0.06]">
          <div className="w-3 h-3 rounded-full bg-[#FF5F57]" />
          <div className="w-3 h-3 rounded-full bg-[#FEBC2E]" />
          <div className="w-3 h-3 rounded-full bg-[#28C840]" />
          <span className="ml-2 text-[11px] font-mono" style={{ color: cat.color }}>
            span · {cat.label.toLowerCase()}
          </span>
          <span className="ml-auto text-[11px] font-mono text-zinc-600">
            {cat.fields.length} fields
          </span>
        </div>
        <div className="p-5 sm:p-6">
          {cat.fields.map((f, i) => (
            <div
              key={f.key}
              className="grid md:grid-cols-[minmax(0,280px)_1fr] gap-1 md:gap-5 py-3.5 border-b border-white/[0.04] first:pt-0 last:border-0 last:pb-0"
              style={{ animation: `lineIn 240ms ease-out ${i * 35}ms both` }}
            >
              <span
                className="font-mono text-[13px] font-medium break-words"
                style={{ color: cat.color }}
              >
                {f.key}
              </span>
              <div className="min-w-0">
                <div className="font-mono text-[12.5px] text-zinc-300 break-words">
                  {f.example}
                </div>
                <div className="text-[12.5px] text-zinc-500 leading-relaxed mt-1">
                  {f.note}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes lineIn {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
