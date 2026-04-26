"use client";

import { Topbar } from "@/components/layout/topbar";
import {
  ArrowRight,
  Database,
  Zap,
  Shield,
  BarChart2,
  GitBranch,
  Globe,
  Lock,
  AlertTriangle,
  CheckCircle2,
  Clock,
  DollarSign,
} from "lucide-react";

// ── Section heading ───────────────────────────────────────────────────────────

function SectionHeading({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: React.ElementType;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="p-2 rounded-lg bg-lime-500/10 flex-shrink-0">
        <Icon className="w-4 h-4 text-lime-400" />
      </div>
      <div>
        <h2 className="text-base font-semibold text-white">{title}</h2>
        <p className="text-xs text-zinc-500 mt-0.5">{subtitle}</p>
      </div>
    </div>
  );
}

// ── Flow arrow ────────────────────────────────────────────────────────────────

function FlowArrow() {
  return (
    <div className="flex justify-center py-1">
      <ArrowRight className="w-4 h-4 text-zinc-700 rotate-90" />
    </div>
  );
}

// ── Flow box ──────────────────────────────────────────────────────────────────

function FlowBox({
  label,
  sublabel,
  color = "zinc",
}: {
  label: string;
  sublabel?: string;
  color?: "zinc" | "lime" | "emerald" | "violet" | "amber";
}) {
  const colors = {
    zinc: "border-zinc-700 bg-zinc-800 text-zinc-300",
    lime: "border-lime-500/30 bg-lime-500/10 text-lime-300",
    emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    violet: "border-violet-500/30 bg-violet-500/10 text-violet-300",
    amber: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  };
  return (
    <div className={`rounded-lg border px-4 py-2.5 text-center ${colors[color]}`}>
      <p className="text-xs font-semibold">{label}</p>
      {sublabel && <p className="text-xs text-zinc-500 mt-0.5">{sublabel}</p>}
    </div>
  );
}

// ── Callout ───────────────────────────────────────────────────────────────────

function Callout({
  icon: Icon,
  color,
  children,
}: {
  icon: React.ElementType;
  color: "blue" | "green" | "amber" | "red";
  children: React.ReactNode;
}) {
  const colors = {
    blue: "bg-blue-500/10 border-blue-500/20 text-blue-300",
    green: "bg-emerald-500/10 border-emerald-500/20 text-emerald-300",
    amber: "bg-amber-500/10 border-amber-500/20 text-amber-300",
    red: "bg-red-500/10 border-red-500/20 text-red-300",
  };
  const iconColors = {
    blue: "text-blue-400",
    green: "text-emerald-400",
    amber: "text-amber-400",
    red: "text-red-400",
  };
  return (
    <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 mt-4 ${colors[color]}`}>
      <Icon className={`w-4 h-4 flex-shrink-0 mt-0.5 ${iconColors[color]}`} />
      <p className="text-sm">{children}</p>
    </div>
  );
}

// ── Prop row ──────────────────────────────────────────────────────────────────

function PropRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-zinc-800 last:border-0">
      <span className="text-xs font-semibold text-zinc-500 w-40 flex-shrink-0 pt-0.5">{label}</span>
      <span className="text-sm text-zinc-400">{value}</span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function HowItWorksPage() {
  return (
    <div>
      <Topbar title="How it Works" />

      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">

        {/* Intro */}
        <div className="bg-lime-500/10 border border-lime-500/20 rounded-xl px-6 py-5">
          <p className="text-sm font-semibold text-lime-300 mb-1">
            whyllm is a transparent proxy and ingest pipeline for LLM traffic.
          </p>
          <p className="text-sm text-zinc-400">
            Your app's LLM calls flow through a local or cloud-hosted proxy. Every request and
            response is captured in real time, enriched with token counts and cost estimates,
            and stored for analysis — without changing how your app works.
          </p>
        </div>

        {/* 1. Proxy architecture */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <SectionHeading
            icon={Globe}
            title="The proxy layer"
            subtitle="Sits between your app and OpenAI / Anthropic. Zero latency overhead."
          />

          <div className="max-w-xs mx-auto mb-6">
            <FlowBox label="Your app" sublabel="Python / TS / Go / …" color="zinc" />
            <FlowArrow />
            <FlowBox label="whyllm proxy" sublabel="localhost:17823" color="lime" />
            <FlowArrow />
            <FlowBox label="OpenAI / Anthropic" sublabel="api.openai.com" color="emerald" />
          </div>

          <p className="text-sm text-zinc-400 mb-3">
            The proxy is a lightweight FastAPI server. It intercepts your request, records the
            metadata, forwards the request byte-for-byte to the upstream LLM provider, then
            streams the response back. Your <strong className="text-zinc-200">own API key</strong> is passed through in the
            original <code className="text-xs bg-zinc-800 text-zinc-300 px-1 rounded">Authorization</code> header
            — whyllm never stores or replaces it.
          </p>

          <div className="space-y-2">
            <PropRow label="Proxy endpoint" value="http://localhost:17823/proxy  →  your configured upstream" />
            <PropRow label="Upstream provider" value="Inferred from the base URL you set at project creation (OpenAI, Azure, Anthropic, Bedrock, custom)" />
            <PropRow label="OTLP endpoint" value="http://localhost:17823/otlp  (existing OTel stacks)" />
            <PropRow label="Your key" value="Passed through unchanged. Never logged, never stored." />
            <PropRow label="Added latency" value="< 1 ms on localhost (pure async passthrough)" />
          </div>

          <Callout icon={Lock} color="blue">
            <strong>Key security:</strong> whyllm only stores token counts, model names, latency,
            and cost. Prompt content and completion text are stored in encrypted spans —
            never your API keys.
          </Callout>
        </div>

        {/* 2. Span capture */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <SectionHeading
            icon={GitBranch}
            title="Span capture and enrichment"
            subtitle="Every LLM call becomes a structured span within microseconds."
          />

          <p className="text-sm text-zinc-400 mb-4">
            When the upstream provider closes the response, the proxy creates a <em>span</em> — a
            structured record of the call. Spans are written to a Redis queue immediately so the
            HTTP response is never delayed by database writes.
          </p>

          <div className="rounded-lg bg-zinc-950 border border-zinc-800 px-4 py-3 text-xs text-zinc-300 font-mono mb-4 overflow-x-auto">
            <pre>{`{
  "span_id":      "01HY...",
  "project_id":   "proj_abc123",
  "model":        "gpt-4o",
  "provider":     "openai",
  "prompt_tokens":  512,
  "completion_tokens": 128,
  "total_tokens":   640,
  "cost_usd":       0.00384,
  "latency_ms":     823,
  "status_code":    200,
  "started_at":   "2025-06-01T12:00:00.123Z",
  "finished_at":  "2025-06-01T12:00:00.946Z"
}`}</pre>
          </div>

          <div className="space-y-2">
            <PropRow label="Token counts" value="Parsed from provider response headers and body" />
            <PropRow label="Cost" value="Calculated client-side using per-token pricing table (updated monthly)" />
            <PropRow label="Latency" value="wall-clock time from first byte sent to last byte received" />
            <PropRow label="Model" value="Extracted from request body (works even if you change models at runtime)" />
          </div>
        </div>

        {/* 3. Ingest pipeline */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <SectionHeading
            icon={Database}
            title="Ingest pipeline"
            subtitle="Redis write queue → background worker → PostgreSQL. Non-blocking by design."
          />

          <div className="max-w-sm mx-auto mb-6">
            <FlowBox label="Proxy handler" sublabel="async FastAPI" color="lime" />
            <FlowArrow />
            <FlowBox label="Redis queue" sublabel="LPUSH  whyllm:spans" color="violet" />
            <FlowArrow />
            <FlowBox label="Worker process" sublabel="BRPOP → batch insert" color="amber" />
            <FlowArrow />
            <FlowBox label="PostgreSQL spans table" sublabel="monthly partitions" color="emerald" />
          </div>

          <div className="space-y-2 mb-4">
            <PropRow label="Queue" value="Redis list (LPUSH/BRPOP). Durable if Redis is persisted." />
            <PropRow label="Batch size" value="Worker flushes up to 200 spans per transaction (configurable)" />
            <PropRow label="Flush interval" value="100 ms — spans appear in the dashboard within ~1 second" />
            <PropRow label="Partitioning" value="spans table is range-partitioned by month — old data stays fast" />
          </div>

          <Callout icon={CheckCircle2} color="green">
            The proxy never waits for the database. If the worker falls behind, spans buffer in
            Redis. If Redis is unavailable, the proxy still forwards requests — spans are dropped
            rather than blocking your app.
          </Callout>
        </div>

        {/* 4. Cost tracking */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <SectionHeading
            icon={DollarSign}
            title="Cost tracking"
            subtitle="Per-model pricing baked in. No external API calls needed."
          />

          <p className="text-sm text-zinc-400 mb-4">
            whyllm ships with a pricing table for all major OpenAI and Anthropic models.
            When a span is created, cost is calculated immediately from the token counts:
          </p>

          <div className="rounded-lg bg-zinc-950 border border-zinc-800 px-4 py-3 text-xs text-zinc-300 font-mono mb-4">
            <pre>{`cost_usd = (prompt_tokens  / 1_000_000 * input_price_per_m)
         + (completion_tokens / 1_000_000 * output_price_per_m)`}</pre>
          </div>

          <div className="space-y-2 mb-4">
            <PropRow label="Granularity" value="Per span — you can filter by model, date, or project" />
            <PropRow label="Rollups" value="Hourly and daily aggregates are pre-computed for the dashboard" />
            <PropRow label="Currency" value="USD (matching provider invoices)" />
            <PropRow label="Pricing updates" value="Table is shipped with the binary; update by deploying a new version" />
          </div>

          <Callout icon={AlertTriangle} color="amber">
            Cost estimates may differ slightly from provider invoices due to rounding. Use the
            dashboard as a directional signal, not a billing replacement.
          </Callout>
        </div>

        {/* 5. Budget enforcement */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <SectionHeading
            icon={Shield}
            title="Budget enforcement"
            subtitle="Hard stops and soft alerts — configured per project."
          />

          <p className="text-sm text-zinc-400 mb-4">
            Budgets are checked at the proxy layer, before the request is forwarded to the
            upstream provider. This means you're never billed for a call that was blocked.
          </p>

          <div className="max-w-xs mx-auto mb-5">
            <FlowBox label="Incoming request" color="zinc" />
            <FlowArrow />
            <FlowBox label="Budget check" sublabel="Redis atomic counter" color="lime" />
            <div className="grid grid-cols-2 gap-2 mt-1">
              <div className="text-center">
                <p className="text-xs text-zinc-500 mb-1">Under budget</p>
                <FlowBox label="Forward to LLM" color="emerald" />
              </div>
              <div className="text-center">
                <p className="text-xs text-zinc-500 mb-1">Over budget</p>
                <FlowBox label="HTTP 429" color="amber" />
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <PropRow label="Counter" value="Running daily spend tracked in Redis (sub-millisecond read)" />
            <PropRow label="Reset" value="Daily counters reset at midnight UTC" />
            <PropRow label="Alert mode" value="Sends a webhook / notification but still forwards the request" />
            <PropRow label="Hard stop" value="Returns HTTP 429 with JSON body describing the limit" />
          </div>
        </div>

        {/* 6. Observability */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <SectionHeading
            icon={BarChart2}
            title="Dashboard and observability"
            subtitle="Traces, cost charts, and live activity — all from the ingested spans."
          />

          <div className="grid grid-cols-2 gap-4 mb-4">
            {[
              {
                label: "Traces",
                desc: "Every span is a trace. Filter by model, status, latency, or date range.",
                icon: GitBranch,
              },
              {
                label: "Cost",
                desc: "Daily and per-model cost breakdown. Export as CSV.",
                icon: DollarSign,
              },
              {
                label: "Latency",
                desc: "p50 / p95 / p99 latency per model and endpoint.",
                icon: Clock,
              },
              {
                label: "Errors",
                desc: "4xx/5xx rates surfaced from upstream provider responses.",
                icon: AlertTriangle,
              },
            ].map(({ label, desc, icon: Icon }) => (
              <div key={label} className="rounded-lg border border-zinc-800 bg-zinc-800/30 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Icon className="w-3.5 h-3.5 text-lime-400" />
                  <span className="text-xs font-semibold text-zinc-200">{label}</span>
                </div>
                <p className="text-xs text-zinc-500">{desc}</p>
              </div>
            ))}
          </div>

          <Callout icon={Zap} color="blue">
            All dashboard queries run against the pre-partitioned PostgreSQL spans table.
            Even at millions of spans per day, the Overview page loads in under 200 ms.
          </Callout>
        </div>

        {/* 7. Data flow summary */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <SectionHeading
            icon={CheckCircle2}
            title="End-to-end data flow"
            subtitle="From API call to dashboard — under 1 second."
          />

          <ol className="space-y-3">
            {[
              "Your app calls the OpenAI SDK with OPENAI_BASE_URL pointing at whyllm.",
              "The proxy authenticates your project key (X-whyllm-Key header) and checks the budget counter.",
              "The request is forwarded byte-for-byte to OpenAI. Your API key travels in the Authorization header, untouched.",
              "The response streams back. As the last byte arrives, the proxy creates a span with token counts, cost, and latency.",
              "The span is pushed to Redis (LPUSH). The HTTP response is returned to your app.",
              "The background worker picks up the span (BRPOP), batches it with others, and inserts into PostgreSQL.",
              "Within ~1 second, the span appears in Traces. Cost rolls up in the dashboard within the minute.",
            ].map((step, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-lime-500/10 text-lime-400 border border-lime-500/20 text-xs font-bold flex-shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <p className="text-sm text-zinc-400">{step}</p>
              </li>
            ))}
          </ol>
        </div>

      </div>
    </div>
  );
}
