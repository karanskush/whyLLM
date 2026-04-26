"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ThumbsUp,
  ThumbsDown,
  Flag,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
} from "lucide-react";
import {
  spans,
  type SpanDetailResponse,
  type SpanListItem,
  type SpanTimings,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Design tokens ─────────────────────────────────────────────────────────────
// Labels: uppercase micro-caps that do the work of headings.
// Numbers: tabular, medium weight, tight tracking.
// Color is never decorative — only lime (positive), amber (attention),
// red (error) carry meaning. Everything else is zinc.

const LABEL =
  "text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500";
const HAIRLINE = "border-zinc-800/70";

// ── Atoms ─────────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const color =
    status === "success"
      ? "bg-lime-400"
      : status === "error"
        ? "bg-red-400"
        : "bg-amber-400";
  return (
    <span className="inline-flex items-center gap-1.5 text-zinc-400 text-xs">
      <span className={cn("w-1.5 h-1.5 rounded-full", color)} />
      <span className="capitalize">{status}</span>
    </span>
  );
}

function CopyButton({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
      title="Copy"
      className={cn(
        "inline-flex items-center justify-center w-5 h-5 rounded text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors",
        className,
      )}
    >
      {copied ? (
        <Check className="w-3 h-3 text-lime-400" />
      ) : (
        <Copy className="w-3 h-3" />
      )}
    </button>
  );
}

function Section({
  label,
  right,
  children,
  className,
}: {
  label?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={className}>
      {(label || right) && (
        <div className="flex items-center justify-between mb-3">
          {label && <h3 className={LABEL}>{label}</h3>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

// ── Header ────────────────────────────────────────────────────────────────────

function Header({ span }: { span: SpanDetailResponse }) {
  const router = useRouter();
  const started = span.started_at ? new Date(span.started_at) : null;
  return (
    <div className={cn("border-b px-6 lg:px-10 py-6", HAIRLINE)}>
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-3 mb-5">
          <button
            onClick={() => router.push("/dashboard/traces")}
            className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-200 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Traces</span>
          </button>
          <span className="text-zinc-700">/</span>
          <div className="flex items-center gap-1 min-w-0">
            <span className="font-mono text-xs text-zinc-400 truncate">
              {span.id}
            </span>
            <CopyButton value={span.id} />
          </div>
        </div>

        <div className="flex items-end gap-5 flex-wrap">
          <h1 className="text-2xl font-medium text-zinc-50 tracking-tight leading-none">
            {span.model}
          </h1>
          <div className="flex items-center gap-3 text-xs text-zinc-500 pb-0.5">
            <StatusDot status={span.status} />
            <span className="text-zinc-700">·</span>
            <span className="capitalize">{span.provider}</span>
            {span.environment && (
              <>
                <span className="text-zinc-700">·</span>
                <span>{span.environment}</span>
              </>
            )}
            {started && (
              <>
                <span className="text-zinc-700">·</span>
                <span>{started.toLocaleString()}</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Stat bar ──────────────────────────────────────────────────────────────────

function Stat({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "warn" | "danger";
}) {
  const valueTone =
    tone === "warn"
      ? "text-amber-300"
      : tone === "danger"
        ? "text-red-300"
        : "text-zinc-50";
  return (
    <div className="flex-1 min-w-[120px] px-5 py-4 first:pl-0">
      <div className={LABEL}>{label}</div>
      <div
        className={cn(
          "mt-1.5 text-xl font-medium tracking-tight tabular-nums",
          valueTone,
        )}
      >
        {value}
      </div>
      {sub && <div className="text-[11px] text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function StatBar({ span }: { span: SpanDetailResponse }) {
  const hallScore = span.hallucination_score
    ? parseFloat(span.hallucination_score)
    : null;
  const hallTone: "default" | "warn" | "danger" =
    hallScore === null
      ? "default"
      : hallScore > 0.5
        ? "danger"
        : hallScore > 0.3
          ? "warn"
          : "default";

  return (
    <div
      className={cn(
        "flex items-stretch border rounded-lg bg-zinc-900/40 divide-x overflow-x-auto",
        HAIRLINE,
        "divide-zinc-800/70",
      )}
    >
      <Stat
        label="Latency"
        value={
          span.latency_ms !== null
            ? `${((span.proxy_overhead_ms ?? 0) + span.latency_ms).toLocaleString()} ms`
            : "—"
        }
        sub={(() => {
          const parts: string[] = [];
          if (span.proxy_overhead_ms !== null && span.proxy_overhead_ms > 0)
            parts.push(`overhead ${span.proxy_overhead_ms}ms`);
          if (span.ttft_ms !== null) parts.push(`ttft ${span.ttft_ms}ms`);
          return parts.length > 0 ? parts.join(" · ") : undefined;
        })()}
      />
      <Stat
        label="Tokens"
        value={span.total_tokens?.toLocaleString() ?? "—"}
        sub={
          span.input_tokens !== null && span.output_tokens !== null
            ? `${span.input_tokens.toLocaleString()} in · ${span.output_tokens.toLocaleString()} out`
            : undefined
        }
      />
      <Stat
        label="Cost"
        value={
          span.cost_usd ? `$${parseFloat(span.cost_usd).toFixed(6)}` : "—"
        }
      />
      <Stat
        label="Hallucination"
        value={hallScore !== null ? hallScore.toFixed(2) : "—"}
        tone={hallTone}
      />
    </div>
  );
}

// ── Inline alerts ─────────────────────────────────────────────────────────────

type AlertTone = "warn" | "danger" | "info";

function InlineAlert({
  tone,
  title,
  children,
}: {
  tone: AlertTone;
  title: string;
  children?: React.ReactNode;
}) {
  const accent =
    tone === "warn"
      ? "border-amber-400/60 text-amber-200"
      : tone === "danger"
        ? "border-red-400/60 text-red-200"
        : "border-lime-400/60 text-lime-200";
  const body =
    tone === "warn"
      ? "text-amber-200/70"
      : tone === "danger"
        ? "text-red-200/70"
        : "text-lime-200/70";
  return (
    <div className={cn("border-l-2 pl-4 py-2", accent)}>
      <div className="text-sm font-medium leading-tight">{title}</div>
      {children && (
        <div className={cn("text-xs mt-1 leading-relaxed", body)}>
          {children}
        </div>
      )}
    </div>
  );
}

// ── Token breakdown ───────────────────────────────────────────────────────────

type TokenDetails = {
  cachedInput: number;
  freshInput: number;
  reasoningOutput: number;
  visibleOutput: number;
};

function extractTokenDetails(
  response: Record<string, unknown> | null,
  fallbackInput: number | null,
  fallbackOutput: number | null,
): TokenDetails {
  const usage =
    (response?.usage as Record<string, unknown> | undefined) ?? undefined;

  const inputTotal =
    (usage?.prompt_tokens as number | undefined) ??
    (usage?.input_tokens as number | undefined) ??
    fallbackInput ??
    0;
  const outputTotal =
    (usage?.completion_tokens as number | undefined) ??
    (usage?.output_tokens as number | undefined) ??
    fallbackOutput ??
    0;

  const promptDetails =
    (usage?.prompt_tokens_details as Record<string, unknown> | undefined) ?? {};
  const completionDetails =
    (usage?.completion_tokens_details as Record<string, unknown> | undefined) ??
    {};

  const cachedInput = (promptDetails.cached_tokens as number | undefined) ?? 0;
  const freshInput = Math.max(inputTotal - cachedInput, 0);

  const reasoningOutput =
    (completionDetails.reasoning_tokens as number | undefined) ?? 0;
  const visibleOutput = Math.max(outputTotal - reasoningOutput, 0);

  return { cachedInput, freshInput, reasoningOutput, visibleOutput };
}

function LegendRow({
  dot,
  label,
  value,
  share,
  muted,
}: {
  dot: string;
  label: string;
  value: number;
  share: number;
  muted?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", dot)} />
      <span
        className={cn(
          "text-[13px] flex-1",
          muted ? "text-zinc-500" : "text-zinc-300",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "text-[13px] font-mono tabular-nums",
          muted ? "text-zinc-500" : "text-zinc-200",
        )}
      >
        {value.toLocaleString()}
      </span>
      <span className="text-[11px] text-zinc-600 tabular-nums w-10 text-right">
        {share.toFixed(0)}%
      </span>
    </div>
  );
}

function TokenBreakdown({ details }: { details: TokenDetails }) {
  const { cachedInput, freshInput, reasoningOutput, visibleOutput } = details;
  const inputTotal = cachedInput + freshInput;
  const outputTotal = reasoningOutput + visibleOutput;
  const grandTotal = inputTotal + outputTotal;

  if (grandTotal === 0) {
    return (
      <Section label="Tokens">
        <p className="text-sm text-zinc-500">No token usage reported.</p>
      </Section>
    );
  }

  const pct = (n: number) => (n / grandTotal) * 100;
  const share = (n: number, total: number) =>
    total > 0 ? (n / total) * 100 : 0;

  return (
    <Section
      label="Tokens"
      right={
        <span className="text-xs text-zinc-500 tabular-nums">
          {grandTotal.toLocaleString()} total
        </span>
      }
    >
      <div className="flex h-1.5 w-full rounded-full overflow-hidden bg-zinc-800/80 mb-4">
        {cachedInput > 0 && (
          <div className="bg-zinc-400/70" style={{ width: `${pct(cachedInput)}%` }} />
        )}
        {freshInput > 0 && (
          <div className="bg-zinc-200" style={{ width: `${pct(freshInput)}%` }} />
        )}
        {reasoningOutput > 0 && (
          <div className="bg-amber-400/80" style={{ width: `${pct(reasoningOutput)}%` }} />
        )}
        {visibleOutput > 0 && (
          <div className="bg-lime-400" style={{ width: `${pct(visibleOutput)}%` }} />
        )}
      </div>

      <div className="grid md:grid-cols-2 md:gap-8">
        <div>
          <div className={cn(LABEL, "mb-1")}>Input · {inputTotal.toLocaleString()}</div>
          <LegendRow
            dot="bg-zinc-400/70"
            label="Cached"
            value={cachedInput}
            share={share(cachedInput, inputTotal)}
            muted={cachedInput === 0}
          />
          <LegendRow
            dot="bg-zinc-200"
            label="Fresh"
            value={freshInput}
            share={share(freshInput, inputTotal)}
          />
        </div>
        <div>
          <div className={cn(LABEL, "mb-1")}>Output · {outputTotal.toLocaleString()}</div>
          <LegendRow
            dot="bg-amber-400/80"
            label="Reasoning (hidden)"
            value={reasoningOutput}
            share={share(reasoningOutput, outputTotal)}
            muted={reasoningOutput === 0}
          />
          <LegendRow
            dot="bg-lime-400"
            label="Visible"
            value={visibleOutput}
            share={share(visibleOutput, outputTotal)}
          />
        </div>
      </div>
    </Section>
  );
}

// ── Latency breakdown ─────────────────────────────────────────────────────────

function MetricRow({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-zinc-600" />
      <span className="text-[13px] flex-1 text-zinc-300">{label}</span>
      <span className="text-[13px] font-mono tabular-nums text-zinc-200">
        {value}
      </span>
      <span className="text-[11px] text-zinc-600 tabular-nums w-10 text-right">
        {unit}
      </span>
    </div>
  );
}

function LatencyBreakdown({
  upstreamMs,
  ttftMs,
  overheadMs,
  timings,
  outputTokens,
  reasoningTokens,
}: {
  upstreamMs: number | null;
  ttftMs: number | null;
  overheadMs: number | null;
  timings: SpanTimings | null;
  outputTokens: number;
  reasoningTokens: number;
}) {
  if (upstreamMs === null || upstreamMs < 0) return null;

  const safeOverhead = overheadMs !== null && overheadMs >= 0 ? overheadMs : 0;

  // Split "upstream" further when the provider reported its own processing_ms.
  // Streaming: provider_processing_ms covers *prefill* (arrived in headers
  //   before the stream body), so network_rtt = ttft − provider_processing.
  // Non-streaming: covers the whole round trip, so network = latency − provider.
  const providerMs =
    timings?.provider_processing_ms !== undefined
      ? Math.max(0, timings.provider_processing_ms)
      : null;
  const isStreaming = ttftMs !== null;

  let netRttMs: number | null = null;
  let providerPrefillMs: number | null = null;
  let generationMs: number | null = null;
  let providerWholeMs: number | null = null;

  if (isStreaming) {
    providerPrefillMs =
      providerMs !== null ? Math.min(providerMs, ttftMs!) : null;
    netRttMs =
      providerMs !== null ? Math.max(0, ttftMs! - providerPrefillMs!) : null;
    generationMs = Math.max(0, upstreamMs - ttftMs!);
  } else if (providerMs !== null) {
    providerWholeMs = Math.min(providerMs, upstreamMs);
    netRttMs = Math.max(0, upstreamMs - providerWholeMs);
  }

  const totalMs = safeOverhead + upstreamMs;
  const pct = (n: number) => (totalMs > 0 ? (n / totalMs) * 100 : 0);

  // Throughput denominator prefers generation-only time when available.
  const denomMs =
    generationMs !== null && generationMs > 0 ? generationMs : upstreamMs;
  const tokensPerSec =
    outputTokens > 0 && denomMs > 0 ? (outputTokens / denomMs) * 1000 : null;
  const msPerToken =
    outputTokens > 0 && denomMs > 0 ? denomMs / outputTokens : null;

  // Prefill rate = prompt tokens processed per second while provider was "thinking"
  // (only meaningful when we know the prefill window).
  // Note: we don't have input_tokens here; the caller could pass it but for
  // now we expose the throughput we can compute cleanly.

  const hasOverhead = safeOverhead > 0;
  const hasNet = netRttMs !== null && netRttMs >= 0;
  const hasProvider =
    (providerPrefillMs !== null && providerPrefillMs >= 0) ||
    (providerWholeMs !== null && providerWholeMs >= 0);

  return (
    <Section
      label="Latency"
      right={
        <span className="text-xs text-zinc-500 tabular-nums">
          {totalMs.toLocaleString()} ms total
        </span>
      }
    >
      <div className="flex h-1.5 w-full rounded-full overflow-hidden bg-zinc-800/80 mb-4">
        {hasOverhead && (
          <div
            className="bg-zinc-400/70"
            style={{ width: `${pct(safeOverhead)}%` }}
          />
        )}
        {hasNet && (
          <div
            className="bg-sky-400/70"
            style={{ width: `${pct(netRttMs!)}%` }}
          />
        )}
        {isStreaming ? (
          <>
            {hasProvider ? (
              <div
                className="bg-amber-400/80"
                style={{ width: `${pct(providerPrefillMs!)}%` }}
              />
            ) : (
              <div
                className="bg-amber-400/80"
                style={{ width: `${pct(ttftMs!)}%` }}
              />
            )}
            <div
              className="bg-lime-400"
              style={{ width: `${pct(generationMs!)}%` }}
            />
          </>
        ) : hasProvider ? (
          <div
            className="bg-amber-400/80"
            style={{ width: `${pct(providerWholeMs!)}%` }}
          />
        ) : (
          <div
            className="bg-lime-400"
            style={{ width: `${pct(upstreamMs)}%` }}
          />
        )}
      </div>

      <div className="grid md:grid-cols-2 md:gap-8">
        <div>
          <div className={cn(LABEL, "mb-1")}>Breakdown</div>
          <LegendRow
            dot="bg-zinc-400/70"
            label="whyllm overhead"
            value={safeOverhead}
            share={pct(safeOverhead)}
            muted={!hasOverhead}
          />
          {hasNet && (
            <LegendRow
              dot="bg-sky-400/70"
              label="Network RTT"
              value={netRttMs!}
              share={pct(netRttMs!)}
            />
          )}
          {isStreaming ? (
            <>
              <LegendRow
                dot="bg-amber-400/80"
                label={hasProvider ? "Provider prefill" : "Upstream prefill"}
                value={hasProvider ? providerPrefillMs! : ttftMs!}
                share={pct(hasProvider ? providerPrefillMs! : ttftMs!)}
              />
              <LegendRow
                dot="bg-lime-400"
                label="Generation"
                value={generationMs!}
                share={pct(generationMs!)}
              />
            </>
          ) : hasProvider ? (
            <LegendRow
              dot="bg-amber-400/80"
              label="Provider processing"
              value={providerWholeMs!}
              share={pct(providerWholeMs!)}
            />
          ) : (
            <LegendRow
              dot="bg-lime-400"
              label="Upstream (non-streaming)"
              value={upstreamMs}
              share={pct(upstreamMs)}
            />
          )}
        </div>
        <div>
          <div className={cn(LABEL, "mb-1")}>Throughput</div>
          {tokensPerSec !== null && msPerToken !== null ? (
            <>
              <MetricRow
                label="Output rate"
                value={tokensPerSec.toFixed(1)}
                unit="tok/s"
              />
              <MetricRow
                label="Time per token"
                value={msPerToken.toFixed(1)}
                unit="ms"
              />
              {reasoningTokens > 0 && (
                <div className="text-[11px] text-zinc-600 mt-1.5">
                  Includes {reasoningTokens.toLocaleString()} reasoning tokens.
                </div>
              )}
            </>
          ) : (
            <div className="text-[13px] text-zinc-500 py-1.5">
              No output tokens reported.
            </div>
          )}
          {timings?.provider_request_id && (
            <div className="flex items-center gap-2 mt-3 pt-3 border-t border-zinc-800/70">
              <span className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">
                Provider ID
              </span>
              <code className="text-[11px] font-mono text-zinc-400 truncate flex-1">
                {timings.provider_request_id}
              </code>
              <CopyButton value={timings.provider_request_id} />
            </div>
          )}
        </div>
      </div>
    </Section>
  );
}

// ── Streaming rhythm sparkline ────────────────────────────────────────────────
// Plots per-chunk arrivals over time. Stalls (gaps ≥ 500ms) are highlighted —
// they often point to model hiccups or provider backpressure.

function StreamingRhythm({ timings }: { timings: SpanTimings | null }) {
  const timeline = timings?.timeline;
  if (!timeline || timeline.length < 2) return null;

  const firstMs = timeline[0][0];
  const lastMs = timeline[timeline.length - 1][0];
  const duration = Math.max(1, lastMs - firstMs);
  const maxBytes = Math.max(...timeline.map(([, b]) => b), 1);

  const stalls = timings?.stalls ?? [];

  return (
    <Section
      label="Streaming rhythm"
      right={
        <span className="text-xs text-zinc-500 tabular-nums">
          {timings?.chunk_count?.toLocaleString() ?? timeline.length} chunks
        </span>
      }
    >
      <div className="relative w-full h-16 border border-zinc-800/70 rounded bg-zinc-900/30 overflow-hidden">
        {/* Stall bands in red */}
        {stalls.map((s, i) => {
          const left = ((s.at_ms - firstMs) / duration) * 100;
          const width = (s.duration_ms / duration) * 100;
          return (
            <div
              key={`stall-${i}`}
              className="absolute top-0 bottom-0 bg-red-500/15 border-x border-red-500/30"
              style={{
                left: `${Math.max(0, left)}%`,
                width: `${Math.min(100 - left, width)}%`,
              }}
              title={`Stall ${s.duration_ms}ms at ${s.at_ms}ms`}
            />
          );
        })}
        {/* Chunk ticks — height proportional to chunk size */}
        {timeline.map(([t, b], i) => {
          const left = ((t - firstMs) / duration) * 100;
          const height = Math.max(10, (b / maxBytes) * 100);
          return (
            <div
              key={i}
              className="absolute bottom-0 w-px bg-lime-400/70"
              style={{ left: `${left}%`, height: `${height}%` }}
            />
          );
        })}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 mt-3">
        {timings?.inter_chunk_p50_ms !== undefined && (
          <MetricRow
            label="Gap p50"
            value={timings.inter_chunk_p50_ms.toString()}
            unit="ms"
          />
        )}
        {timings?.inter_chunk_p95_ms !== undefined && (
          <MetricRow
            label="Gap p95"
            value={timings.inter_chunk_p95_ms.toString()}
            unit="ms"
          />
        )}
        {timings?.inter_chunk_max_ms !== undefined && (
          <MetricRow
            label="Gap max"
            value={timings.inter_chunk_max_ms.toString()}
            unit="ms"
          />
        )}
        {timings?.stall_count !== undefined && timings.stall_count > 0 && (
          <MetricRow
            label="Stalls"
            value={`${timings.stall_count} · ${timings.stall_total_ms ?? 0}`}
            unit="ms"
          />
        )}
      </div>
    </Section>
  );
}

// ── Finish reason + content filter ────────────────────────────────────────────

const FINISH_REASON_COPY: Record<
  string,
  { tone: AlertTone; hint: string }
> = {
  stop: { tone: "info", hint: "Model emitted a natural stop token." },
  length: {
    tone: "warn",
    hint: "Output cut off by max_tokens / max_completion_tokens — raise the limit to get a full answer.",
  },
  content_filter: {
    tone: "danger",
    hint: "Provider safety filter blocked the response.",
  },
  tool_calls: {
    tone: "info",
    hint: "Model chose to call a tool instead of replying in text.",
  },
  function_call: { tone: "info", hint: "Function call requested." },
};

// Only surface finish reason when it's noteworthy (not a clean "stop").
function NoteworthyFinishReason({ reason }: { reason: string | null }) {
  if (!reason || reason === "stop" || reason === "tool_calls") return null;
  const meta = FINISH_REASON_COPY[reason] ?? {
    tone: "warn" as const,
    hint: "",
  };
  return (
    <InlineAlert tone={meta.tone} title={`Finish reason: ${reason}`}>
      {meta.hint}
    </InlineAlert>
  );
}

type FilterCategory = {
  key: string;
  filtered: boolean;
  severity?: string;
  detected?: boolean;
};

function collectFilterCategories(
  response: Record<string, unknown> | null,
): FilterCategory[] {
  if (!response) return [];
  const seen = new Map<string, FilterCategory>();
  const visit = (block: unknown) => {
    if (!block || typeof block !== "object") return;
    for (const [key, val] of Object.entries(block as Record<string, unknown>)) {
      if (!val || typeof val !== "object") continue;
      const entry = val as Record<string, unknown>;
      if ("filtered" in entry) {
        seen.set(key, {
          key,
          filtered: Boolean(entry.filtered),
          severity: entry.severity as string | undefined,
          detected: entry.detected as boolean | undefined,
        });
      }
    }
  };
  const promptFilters = response.prompt_filter_results as
    | Array<Record<string, unknown>>
    | undefined;
  if (Array.isArray(promptFilters))
    for (const p of promptFilters) visit(p.content_filter_results);
  const choices = response.choices as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(choices)) for (const c of choices) visit(c.content_filter_results);
  return Array.from(seen.values());
}

function SafetyFilters({ categories }: { categories: FilterCategory[] }) {
  if (categories.length === 0) return null;
  const flagged = categories.filter(
    (c) => c.filtered || c.detected === true || (c.severity && c.severity !== "safe"),
  );
  const allClear = flagged.length === 0;

  return (
    <Section
      label="Safety filters"
      right={
        <span
          className={cn(
            "text-[11px] font-medium",
            allClear ? "text-lime-400" : "text-red-300",
          )}
        >
          {allClear ? "All clear" : `${flagged.length} flagged`}
        </span>
      }
    >
      <div className="flex flex-wrap gap-1.5">
        {categories.map((c) => {
          const isFlagged =
            c.filtered ||
            c.detected === true ||
            (c.severity && c.severity !== "safe");
          return (
            <span
              key={c.key}
              className={cn(
                "inline-flex items-center gap-1.5 text-[11px] tabular-nums px-2 py-0.5 rounded border",
                isFlagged
                  ? "border-red-400/40 text-red-200 bg-red-500/5"
                  : "border-zinc-800 text-zinc-500",
              )}
              title={
                c.severity
                  ? `${c.key}: severity=${c.severity}`
                  : c.detected !== undefined
                    ? `${c.key}: detected=${c.detected}`
                    : c.key
              }
            >
              <span
                className={cn(
                  "w-1 h-1 rounded-full",
                  isFlagged ? "bg-red-400" : "bg-zinc-600",
                )}
              />
              {c.key.replace(/_/g, " ")}
              {c.severity && c.severity !== "safe" && (
                <span className="text-red-300/70">· {c.severity}</span>
              )}
            </span>
          );
        })}
      </div>
    </Section>
  );
}

// ── Conversation (Linear comment-style) ───────────────────────────────────────

type ChatMessage = { role: string; content: string };

function extractMessages(
  request: Record<string, unknown> | null,
  response: Record<string, unknown> | null,
): { prompt: ChatMessage[]; completion: ChatMessage | null } {
  const prompt: ChatMessage[] = [];
  if (request) {
    const msgs = request.messages as Array<Record<string, unknown>> | undefined;
    if (Array.isArray(msgs)) {
      for (const m of msgs) {
        const content = m.content;
        prompt.push({
          role: (m.role as string) || "user",
          content:
            typeof content === "string"
              ? content
              : Array.isArray(content)
                ? content
                    .map((p: unknown) =>
                      typeof p === "object" && p && "text" in p
                        ? String((p as { text: unknown }).text ?? "")
                        : JSON.stringify(p),
                    )
                    .join("\n")
                : JSON.stringify(content ?? ""),
        });
      }
    }
    const inputStr = request.input;
    if (prompt.length === 0 && typeof inputStr === "string" && inputStr.length > 0) {
      prompt.push({ role: "user", content: inputStr });
    }
  }

  let completion: ChatMessage | null = null;
  if (response) {
    const choices = response.choices as Array<Record<string, unknown>> | undefined;
    if (Array.isArray(choices) && choices[0]) {
      const msg = choices[0].message as Record<string, unknown> | undefined;
      if (msg) {
        completion = {
          role: (msg.role as string) || "assistant",
          content: (msg.content as string) ?? "",
        };
      }
    }
    if (!completion) {
      const content = response.content as Array<Record<string, unknown>> | undefined;
      if (Array.isArray(content)) {
        const text = content
          .filter((b) => b.type === "text")
          .map((b) => b.text as string)
          .join("");
        if (text) completion = { role: "assistant", content: text };
      }
    }
  }
  return { prompt, completion };
}

function roleDot(role: string) {
  switch (role) {
    case "system":
      return "bg-zinc-500";
    case "assistant":
      return "bg-lime-400";
    case "tool":
      return "bg-zinc-400";
    case "user":
    default:
      return "bg-zinc-200";
  }
}

function Message({
  message,
  emptyHint,
  isLast,
}: {
  message: ChatMessage;
  emptyHint?: string;
  isLast?: boolean;
}) {
  const isEmpty = !message.content || message.content.length === 0;

  return (
    <div className="group relative pl-6 pb-5 last:pb-0">
      {/* Rail */}
      {!isLast && (
        <div className="absolute left-[3px] top-3 bottom-0 w-px bg-zinc-800/70" />
      )}
      <span
        className={cn(
          "absolute left-0 top-[5px] w-[7px] h-[7px] rounded-full",
          roleDot(message.role),
        )}
      />
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-[0.12em] font-medium text-zinc-400">
          {message.role}
        </span>
        {!isEmpty && (
          <span className="opacity-0 group-hover:opacity-100 transition-opacity">
            <CopyButton value={message.content} />
          </span>
        )}
      </div>
      {isEmpty ? (
        <p className="text-[13px] italic text-zinc-500 leading-relaxed">
          {emptyHint ?? "(empty)"}
        </p>
      ) : (
        <pre className="whitespace-pre-wrap break-words text-[13.5px] text-zinc-200 leading-relaxed font-sans">
          {message.content}
        </pre>
      )}
    </div>
  );
}

function Conversation({
  prompt,
  completion,
  completionEmptyHint,
}: {
  prompt: ChatMessage[];
  completion: ChatMessage | null;
  completionEmptyHint?: string;
}) {
  if (prompt.length === 0 && !completion) return null;
  const items = [...prompt];
  if (completion) items.push(completion);

  return (
    <Section label="Conversation">
      <div>
        {items.map((m, i) => (
          <Message
            key={i}
            message={m}
            isLast={i === items.length - 1}
            emptyHint={
              m === completion && completion.content === ""
                ? completionEmptyHint
                : undefined
            }
          />
        ))}
      </div>
    </Section>
  );
}

// ── Raw payload viewer ────────────────────────────────────────────────────────

function JsonViewer({
  data,
  label,
}: {
  data: Record<string, unknown> | null;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const json = JSON.stringify(data, null, 2);

  return (
    <div className={cn("border rounded-lg overflow-hidden", HAIRLINE)}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-zinc-900/50 text-left transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          {open ? (
            <ChevronDown className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
          )}
          <span className="text-[13px] text-zinc-300">{label}</span>
          <span className="text-[11px] text-zinc-600">
            {Object.keys(data).length} keys
          </span>
        </div>
        {open && <CopyButton value={json} />}
      </button>
      {open && (
        <pre
          className={cn(
            "p-4 text-[11.5px] leading-relaxed font-mono text-zinc-400 bg-zinc-950 overflow-x-auto max-h-96 border-t",
            HAIRLINE,
          )}
        >
          {json}
        </pre>
      )}
    </div>
  );
}

// ── Sidebar: Timeline mini ────────────────────────────────────────────────────

function Timeline({
  span,
  siblings,
}: {
  span: SpanDetailResponse;
  siblings: SpanListItem[];
}) {
  const all = [span as SpanListItem, ...siblings].filter((s) => s.started_at);
  if (all.length < 2) return null;
  const traceStart = Math.min(
    ...all.map((s) => new Date(s.started_at!).getTime()),
  );
  const traceEnd = Math.max(
    ...all.map((s) => new Date(s.started_at!).getTime() + (s.latency_ms ?? 0)),
  );
  const duration = Math.max(traceEnd - traceStart, 1);

  return (
    <Section
      label="Timeline"
      right={
        <span className="text-[11px] text-zinc-500 tabular-nums">
          {duration.toLocaleString()}ms · {all.length} spans
        </span>
      }
    >
      <div className="space-y-1.5">
        {all
          .slice()
          .sort(
            (a, b) =>
              new Date(a.started_at!).getTime() -
              new Date(b.started_at!).getTime(),
          )
          .map((s) => {
            const start = new Date(s.started_at!).getTime();
            const leftPct = ((start - traceStart) / duration) * 100;
            const widthPct = Math.max(((s.latency_ms ?? 50) / duration) * 100, 0.8);
            const isCurrent = s.id === span.id;
            return (
              <div key={s.id} className="group flex items-center gap-2">
                <div className="w-16 text-[10px] font-mono text-zinc-500 truncate text-right flex-shrink-0">
                  {s.model.split("-").slice(-2).join("-")}
                </div>
                <div className="flex-1 relative h-3 rounded-sm bg-zinc-900/70">
                  <div
                    className={cn(
                      "absolute top-0.5 h-2 rounded-sm",
                      isCurrent
                        ? "bg-lime-400"
                        : s.status === "error"
                          ? "bg-red-400/60"
                          : "bg-zinc-600",
                    )}
                    style={{
                      left: `${Math.min(leftPct, 99)}%`,
                      width: `${Math.max(Math.min(widthPct, 100 - leftPct), 0.8)}%`,
                    }}
                  />
                </div>
                <div className="w-12 text-[10px] text-zinc-500 tabular-nums text-right flex-shrink-0">
                  {s.latency_ms !== null ? `${s.latency_ms}ms` : "—"}
                </div>
              </div>
            );
          })}
      </div>
    </Section>
  );
}

// ── Sidebar: Definition list ──────────────────────────────────────────────────

function DefRow({
  label,
  value,
  mono,
  copy,
}: {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
  copy?: boolean;
}) {
  const empty = !value;
  return (
    <div className="grid grid-cols-[6rem_1fr_auto] gap-2 items-center py-1.5 border-b border-zinc-800/50 last:border-b-0">
      <span className="text-[11px] text-zinc-500">{label}</span>
      <span
        className={cn(
          "text-[12px] truncate",
          empty ? "text-zinc-600" : "text-zinc-300",
          mono && "font-mono",
        )}
        title={value ?? undefined}
      >
        {value ?? "—"}
      </span>
      {copy && value ? <CopyButton value={value} /> : <span />}
    </div>
  );
}

function MetadataList({ span }: { span: SpanDetailResponse }) {
  return (
    <Section label="Identifiers">
      <div>
        <DefRow label="Span" value={span.id} mono copy />
        <DefRow label="Trace" value={span.trace_id} mono copy />
        <DefRow label="Parent" value={span.parent_span_id} mono copy />
        <DefRow label="Project" value={span.project_id} mono copy />
        <DefRow label="Source" value={span.source} />
        <DefRow label="SDK" value={span.sdk_version} />
        <DefRow label="User" value={span.user_id} />
        <DefRow label="Session" value={span.session_id} />
      </div>
    </Section>
  );
}

// ── Sidebar: Feedback ─────────────────────────────────────────────────────────

function FeedbackPanel({
  spanId,
  token,
  existingFeedback,
}: {
  spanId: string;
  token: string;
  existingFeedback?: string;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [selected, setSelected] = useState<string | null>(
    existingFeedback ?? null,
  );
  const { mutate, isPending } = useMutation({
    mutationFn: (feedback: string) =>
      spans.feedback(spanId, { feedback, note: note || undefined }, token),
    onSuccess: (_, feedback) => {
      setSelected(feedback);
      queryClient.invalidateQueries({ queryKey: ["span", spanId] });
    },
  });

  const options = [
    { value: "positive", icon: ThumbsUp, label: "Good" },
    { value: "negative", icon: ThumbsDown, label: "Bad" },
    { value: "flagged", icon: Flag, label: "Flag" },
  ] as const;

  return (
    <Section label="Feedback">
      <div className="flex items-center gap-1.5">
        {options.map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            onClick={() => mutate(value)}
            disabled={isPending}
            className={cn(
              "flex-1 inline-flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md border text-[12px] transition-colors",
              selected === value
                ? "bg-lime-400 text-zinc-950 border-lime-400"
                : "text-zinc-400 border-zinc-800 hover:text-zinc-200 hover:border-zinc-700",
            )}
          >
            <Icon className="w-3 h-3" />
            {label}
          </button>
        ))}
      </div>
      {selected === "flagged" && (
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add a note…"
          maxLength={500}
          className="mt-2 w-full text-[12px] bg-zinc-900/60 border border-zinc-800 rounded-md p-2 text-zinc-200 placeholder:text-zinc-600 resize-none h-14 focus:outline-none focus:border-zinc-700 transition-colors"
        />
      )}
    </Section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SpanDetailPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const params = useParams<{ span_id: string }>();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  const { data: span, isLoading, isError } = useQuery({
    queryKey: ["span", params.span_id],
    queryFn: () => spans.get(params.span_id, token!),
    enabled: !!token,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 text-xs text-zinc-500">
        Loading span…
      </div>
    );
  }

  if (isError || !span) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <div className="text-center">
          <AlertTriangle className="w-7 h-7 text-red-400 mx-auto mb-3" />
          <p className="text-sm text-zinc-400">Span not found</p>
          <button
            onClick={() => router.push("/dashboard/traces")}
            className="mt-3 text-xs text-lime-400 hover:text-lime-300 transition-colors"
          >
            Back to Traces
          </button>
        </div>
      </div>
    );
  }

  const existingFeedback = span.tags?._feedback as string | undefined;
  const tokenDetails = extractTokenDetails(
    span.response,
    span.input_tokens,
    span.output_tokens,
  );
  const { prompt, completion } = extractMessages(span.request, span.response);
  const filterCategories = collectFilterCategories(span.response);
  const finishReason = (() => {
    const choices = span.response?.choices as Array<Record<string, unknown>> | undefined;
    if (Array.isArray(choices) && choices[0]) {
      return (choices[0].finish_reason as string) ?? null;
    }
    const stop = span.response?.stop_reason as string | undefined;
    return stop ?? null;
  })();

  const completionEmptyHint =
    finishReason === "length" && tokenDetails.reasoningOutput > 0
      ? `Response was empty — all ${tokenDetails.reasoningOutput} output tokens went into hidden reasoning before the max_completion_tokens limit was hit.`
      : finishReason === "length"
        ? "Response was empty — output cut off by max token limit."
        : undefined;

  const hasAlerts =
    Boolean(span.error_type) ||
    (finishReason !== null && finishReason !== "stop" && finishReason !== "tool_calls");

  return (
    <div className="flex flex-col min-h-screen bg-zinc-950">
      <Header span={span} />

      <div className="flex-1 px-6 lg:px-10 py-6 w-full">
        <div className="max-w-6xl mx-auto grid lg:grid-cols-[1fr_320px] gap-6 lg:gap-10">
          {/* Main column */}
          <div className="space-y-8 min-w-0">
            <StatBar span={span} />

            {hasAlerts && (
              <div className="space-y-3">
                {span.error_type && (
                  <InlineAlert tone="danger" title={span.error_type}>
                    <span className="font-mono break-words">
                      {span.error_message}
                    </span>
                  </InlineAlert>
                )}
                <NoteworthyFinishReason reason={finishReason} />
              </div>
            )}

            <LatencyBreakdown
              upstreamMs={span.latency_ms}
              ttftMs={span.ttft_ms}
              overheadMs={span.proxy_overhead_ms}
              timings={span.timings}
              outputTokens={
                tokenDetails.visibleOutput + tokenDetails.reasoningOutput
              }
              reasoningTokens={tokenDetails.reasoningOutput}
            />

            <StreamingRhythm timings={span.timings} />

            <TokenBreakdown details={tokenDetails} />

            <Conversation
              prompt={prompt}
              completion={completion}
              completionEmptyHint={completionEmptyHint}
            />

            {filterCategories.length > 0 && (
              <SafetyFilters categories={filterCategories} />
            )}

            {span.hallucination_flags &&
              Object.keys(span.hallucination_flags).length > 0 && (
                <Section label="Hallucination signals">
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(span.hallucination_flags).map(([k, v]) => (
                      <span
                        key={k}
                        className="inline-flex items-center gap-1.5 text-[11px] tabular-nums px-2 py-0.5 rounded border border-amber-400/40 text-amber-200 bg-amber-500/5"
                      >
                        {k} · {(v as number).toFixed(2)}
                      </span>
                    ))}
                  </div>
                </Section>
              )}

            <Section label="Raw">
              <div className="space-y-1.5">
                <JsonViewer data={span.request} label="Request" />
                <JsonViewer data={span.response} label="Response" />
                <JsonViewer
                  data={
                    span.tags && Object.keys(span.tags).length > 0
                      ? span.tags
                      : null
                  }
                  label="Tags"
                />
              </div>
            </Section>
          </div>

          {/* Sidebar */}
          <aside className="space-y-8 lg:sticky lg:top-6 lg:self-start">
            {span.siblings.length > 0 && (
              <Timeline span={span} siblings={span.siblings} />
            )}
            <MetadataList span={span} />
            {token && (
              <FeedbackPanel
                spanId={span.id}
                token={token}
                existingFeedback={existingFeedback}
              />
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
