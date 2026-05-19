import type { Metadata } from "next";
import Link from "next/link";

import { MarketingNav } from "@/components/marketing/nav";
import { MarketingFooter } from "@/components/marketing/footer";

export const metadata: Metadata = {
  title: "What we show — whyllm",
  description:
    "Every detail whyllm captures from each LLM call — request, response, cost, performance, quality, and forward-looking predictions — plus a feature tour and a plan-by-plan comparison.",
};

// ─────────────────────────────────────────────────────────────────────────────
// Data
// ─────────────────────────────────────────────────────────────────────────────

// What gets recorded on every single LLM call that flows through the proxy.
const CAPTURE_GROUPS: {
  n: string;
  title: string;
  color: string;
  body: string;
  fields: string;
}[] = [
  {
    n: "01",
    title: "The request",
    color: "#84CC16",
    body: "Captured exactly as it left your app — the model, the provider, the full prompt or message array, and the sampling parameters you sent.",
    fields: "model · provider · messages / prompt · temperature · top_p · max_tokens · request headers",
  },
  {
    n: "02",
    title: "The response",
    color: "#84CC16",
    body: "The completion in full, with nothing summarised away. The raw provider body is kept verbatim so any call can be audited later.",
    fields: "completion text · finish_reason · raw response body · system_fingerprint",
  },
  {
    n: "03",
    title: "Cost & tokens",
    color: "#60A5FA",
    body: "Input, output, and cached token counts, priced to the exact USD per call from live provider rate cards. No estimates, no rounding.",
    fields: "input / output / cached tokens · cost_usd · cumulative spend",
  },
  {
    n: "04",
    title: "Performance",
    color: "#60A5FA",
    body: "Latency measured end to end — including the small overhead the proxy itself adds — so the number you see is the number that happened.",
    fields: "total latency · time-to-first-token · proxy overhead · timing breakdown",
  },
  {
    n: "05",
    title: "Quality",
    color: "#C084FC",
    body: "A sub-millisecond hallucination score on every response, with the exact heuristic flags that fired. A sampled LLM judge confirms the flagged ones.",
    fields: "hallucination score · hedging · repetition · overconfidence · refusal · sampled LLM judge",
  },
  {
    n: "06",
    title: "Predictions",
    color: "#C084FC",
    body: "Forward-looking insights from the prediction engine — computed server-side on a schedule, with zero action required from you.",
    fields: "cost forecast vs budget · rate-limit ETA · model drift",
  },
];

// The four product pillars.
const FEATURES: { tag: string; title: string; body: string; color: string }[] = [
  {
    tag: "Tracing",
    title: "Full-stack tracing",
    body: "Every LLM call becomes a searchable span — prompt, response, tokens, latency, the lot. Filter by model, environment, user, or feature and drill into any single call in two clicks.",
    color: "#84CC16",
  },
  {
    tag: "Cost",
    title: "Cost control & budgets",
    body: "Not just charts — enforcement. Set budgets per project, key, or user; the proxy returns HTTP 429 before an over-budget call ever reaches the provider. Auto-route to a cheaper model when a threshold trips.",
    color: "#60A5FA",
  },
  {
    tag: "Quality",
    title: "Hallucination detection",
    body: "A fast heuristic scorer runs on every response — hedge ratio, repetition, overconfidence, refusal patterns — in under a millisecond. An LLM judge samples only the flagged spans, so cost stays near zero.",
    color: "#C084FC",
  },
  {
    tag: "Prediction",
    title: "Prediction & control plane",
    body: "Because whyllm sits inline as a proxy, every prediction can become an in-request action. Cost forecasts, rate-limit ETAs, and model-drift alerts surface before they become incidents — not after.",
    color: "#FB923C",
  },
];

// Plan-by-plan feature comparison.
const PLAN_COLUMNS: { name: string; price: string; note: string; highlight?: boolean }[] = [
  { name: "Basic", price: "$0", note: "forever" },
  { name: "Pro", price: "$0.10", note: "per 10k spans", highlight: true },
  { name: "Enterprise", price: "Custom", note: "" },
];

const PLAN_ROWS: { feature: string; values: (string | boolean)[] }[] = [
  { feature: "Spans / month", values: ["50,000", "Unlimited", "Unlimited"] },
  { feature: "History retention", values: ["7 days", "90 days", "Custom"] },
  { feature: "Projects", values: ["1", "Unlimited", "Unlimited"] },
  { feature: "Cost & token dashboard", values: [true, true, true] },
  { feature: "Hallucination scoring", values: [false, true, true] },
  { feature: "Prediction insights", values: [false, true, true] },
  { feature: "Budget enforcement", values: [false, true, true] },
  { feature: "Alerts & webhooks", values: [false, true, true] },
  { feature: "SSO / SAML", values: [false, false, true] },
  { feature: "Self-hosted option", values: [false, false, true] },
  { feature: "SLA guarantee", values: [false, false, true] },
  { feature: "Support", values: ["Community", "Email", "Dedicated"] },
];

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function WhatWeShowPage() {
  return (
    <div className="min-h-screen overflow-x-hidden" style={{ background: "#09090B", color: "#FAFAFA" }}>
      <MarketingNav />

      {/* ── HERO ──────────────────────────────────────────────────────────── */}
      <section className="relative px-6 pt-32 pb-20 overflow-hidden">
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
            width: "600px",
            height: "400px",
            background: "radial-gradient(circle, rgba(132,204,22,0.08) 0%, transparent 70%)",
          }}
        />
        <div className="relative z-10 max-w-3xl mx-auto text-center">
          <p className="text-lime-500 text-xs font-semibold uppercase tracking-widest mb-4">
            What we show
          </p>
          <h1
            className="font-black tracking-tight text-white mb-5"
            style={{ fontSize: "clamp(2.4rem, 5.5vw, 3.8rem)", lineHeight: 1.07 }}
          >
            Every call,{" "}
            <span
              style={{
                background: "linear-gradient(90deg, #84CC16, #a3e635)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              fully x-rayed.
            </span>
          </h1>
          <p className="text-zinc-400 text-base md:text-lg leading-relaxed max-w-xl mx-auto">
            Once a request flows through the whyllm proxy, nothing about it is a
            mystery. Here is exactly what we record, what we surface, and what
            each plan unlocks.
          </p>
        </div>
      </section>

      {/* ── SECTION 1 — WHAT WE CAPTURE ───────────────────────────────────── */}
      <section id="capture" className="px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              Per call
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-white leading-tight">
              Six things we record on every request
            </h2>
            <p className="text-zinc-500 text-base mt-4 max-w-xl mx-auto">
              Each LLM call becomes one immutable span. These are the details on it.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {CAPTURE_GROUPS.map((g) => (
              <div
                key={g.n}
                className="rounded-2xl border border-white/[0.07] p-6 hover:border-white/[0.14] transition-colors duration-300"
                style={{ background: "rgba(255,255,255,0.02)" }}
              >
                <div className="text-xs font-black mb-4 font-mono" style={{ color: g.color }}>
                  {g.n}
                </div>
                <h3 className="text-lg font-bold text-white mb-2.5">{g.title}</h3>
                <p className="text-zinc-400 text-sm leading-relaxed mb-4">{g.body}</p>
                <div
                  className="text-[11px] font-mono leading-relaxed rounded-lg px-3 py-2.5 border"
                  style={{ color: g.color, borderColor: `${g.color}20`, background: `${g.color}08` }}
                >
                  {g.fields}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── SECTION 2 — FEATURE TOUR ──────────────────────────────────────── */}
      <section id="tour" className="px-6 py-20 border-t border-white/[0.05]">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
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

          <div className="grid md:grid-cols-2 gap-6">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="rounded-2xl border border-white/[0.07] p-7 hover:border-white/[0.14] transition-colors duration-300"
                style={{ background: "rgba(255,255,255,0.02)" }}
              >
                <div
                  className="text-[10px] font-bold uppercase tracking-widest mb-4 w-fit px-2.5 py-1 rounded-full border"
                  style={{ color: f.color, borderColor: `${f.color}30`, background: `${f.color}10` }}
                >
                  {f.tag}
                </div>
                <h3 className="text-xl font-bold text-white mb-3">{f.title}</h3>
                <p className="text-zinc-400 text-sm leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── SECTION 3 — PLAN COMPARISON ───────────────────────────────────── */}
      <section id="plans" className="px-6 py-20 border-t border-white/[0.05]">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-lime-500 text-sm font-semibold uppercase tracking-widest mb-3">
              Plans
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-white leading-tight">
              What you get on each plan
            </h2>
            <p className="text-zinc-500 text-base mt-4 max-w-xl mx-auto">
              Same proxy, same capture on every plan. Higher tiers unlock
              enforcement, intelligence, and scale.
            </p>
          </div>

          <div className="rounded-2xl border border-white/[0.08] overflow-hidden">
            {/* Header row — plan names + prices */}
            <div className="grid grid-cols-[1.6fr_1fr_1fr_1fr]">
              <div className="p-4 bg-white/[0.02] border-b border-white/[0.07]" />
              {PLAN_COLUMNS.map((col) => (
                <div
                  key={col.name}
                  className="p-4 text-center border-b border-white/[0.07]"
                  style={{ background: col.highlight ? "rgba(132,204,22,0.05)" : "rgba(255,255,255,0.02)" }}
                >
                  <div
                    className={`text-sm font-bold ${col.highlight ? "text-lime-400" : "text-white"}`}
                  >
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

            {/* Feature rows */}
            {PLAN_ROWS.map((row) => (
              <div
                key={row.feature}
                className="grid grid-cols-[1.6fr_1fr_1fr_1fr] border-b border-white/[0.04] last:border-0"
              >
                <div className="p-4 text-sm text-zinc-300">{row.feature}</div>
                {row.values.map((v, i) => (
                  <div
                    key={i}
                    className="p-4 flex items-center justify-center text-center"
                    style={{
                      background: PLAN_COLUMNS[i].highlight ? "rgba(132,204,22,0.04)" : undefined,
                    }}
                  >
                    {typeof v === "boolean" ? (
                      v ? (
                        <span className="text-lime-400 text-base">✓</span>
                      ) : (
                        <span className="text-zinc-700">—</span>
                      )
                    ) : (
                      <span className="text-sm text-zinc-300">{v}</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>

          {/* CTA */}
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

      <MarketingFooter />
    </div>
  );
}
