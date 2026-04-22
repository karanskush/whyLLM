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
  Clock,
  Zap,
  DollarSign,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { spans, type SpanDetailResponse, type SpanListItem } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "success"
      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
      : status === "error"
        ? "bg-red-500/10 text-red-400 border border-red-500/20"
        : "bg-amber-500/10 text-amber-400 border border-amber-500/20";
  return (
    <span className={cn("px-2 py-0.5 rounded-full text-xs font-medium", color)}>
      {status}
    </span>
  );
}

// ── Metric chip ────────────────────────────────────────────────────────────────

function MetricChip({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2.5">
      <Icon className="w-4 h-4 text-zinc-500" />
      <div>
        <div className="text-xs text-zinc-500">{label}</div>
        <div className="text-sm font-semibold text-zinc-200">{value}</div>
      </div>
    </div>
  );
}

// ── JSON viewer ────────────────────────────────────────────────────────────────

function JsonViewer({
  data,
  label,
}: {
  data: Record<string, unknown> | null;
  label: string;
}) {
  const [open, setOpen] = useState(false);

  if (!data) return null;

  return (
    <div className="border border-zinc-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-zinc-800/50 hover:bg-zinc-800 text-sm font-medium text-zinc-300 transition-colors"
      >
        <span>{label}</span>
        {open ? (
          <ChevronDown className="w-4 h-4 text-zinc-500" />
        ) : (
          <ChevronRight className="w-4 h-4 text-zinc-500" />
        )}
      </button>
      {open && (
        <pre className="p-4 text-xs font-mono text-zinc-400 bg-zinc-950 overflow-x-auto max-h-96">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ── Gantt timeline ─────────────────────────────────────────────────────────────

function GanttTimeline({
  span,
  siblings,
}: {
  span: SpanDetailResponse;
  siblings: SpanListItem[];
}) {
  const allSpans = [
    span as SpanListItem,
    ...siblings,
  ].filter((s) => s.started_at);

  if (allSpans.length < 2) return null;

  const traceStart = Math.min(
    ...allSpans.map((s) => new Date(s.started_at!).getTime()),
  );
  const traceEnd = Math.max(
    ...allSpans.map((s) => {
      const start = new Date(s.started_at!).getTime();
      const latency = s.latency_ms ?? 0;
      return start + latency;
    }),
  );
  const traceDuration = Math.max(traceEnd - traceStart, 1);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-zinc-300 mb-3">
        Trace Timeline ({allSpans.length} spans)
      </h3>
      <div className="space-y-2">
        {allSpans
          .slice()
          .sort(
            (a, b) =>
              new Date(a.started_at!).getTime() -
              new Date(b.started_at!).getTime(),
          )
          .map((s) => {
            const start = new Date(s.started_at!).getTime();
            const leftPct = ((start - traceStart) / traceDuration) * 100;
            const widthPct = Math.max(
              ((s.latency_ms ?? 50) / traceDuration) * 100,
              0.5,
            );
            const isCurrent = s.id === span.id;

            return (
              <div key={s.id} className="flex items-center gap-3">
                <div className="w-24 text-xs text-zinc-500 truncate text-right flex-shrink-0">
                  {s.model.split("-").slice(-2).join("-")}
                </div>
                <div className="flex-1 relative h-6 bg-zinc-800 rounded">
                  <div
                    className={cn(
                      "absolute top-1 h-4 rounded",
                      isCurrent
                        ? "bg-lime-500"
                        : s.status === "error"
                          ? "bg-red-500/60"
                          : "bg-zinc-600",
                    )}
                    style={{
                      left: `${Math.min(leftPct, 99)}%`,
                      width: `${Math.max(Math.min(widthPct, 100 - leftPct), 0.5)}%`,
                    }}
                  />
                </div>
                <div className="w-16 text-xs text-zinc-500 flex-shrink-0">
                  {s.latency_ms !== null ? `${s.latency_ms}ms` : "—"}
                </div>
              </div>
            );
          })}
      </div>
      <div className="flex justify-between mt-2 text-xs text-zinc-700">
        <span>0ms</span>
        <span>{traceDuration}ms</span>
      </div>
    </div>
  );
}

// ── Feedback buttons ──────────────────────────────────────────────────────────

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

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-zinc-300 mb-3">Feedback</h3>
      <div className="flex items-center gap-2">
        {(
          [
            { value: "positive", icon: ThumbsUp, label: "Good" },
            { value: "negative", icon: ThumbsDown, label: "Bad" },
            { value: "flagged", icon: Flag, label: "Flag" },
          ] as const
        ).map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            onClick={() => mutate(value)}
            disabled={isPending}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors",
              selected === value
                ? "bg-lime-500 text-black border-lime-500"
                : "bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-600 hover:text-zinc-200",
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>
      {selected === "flagged" && (
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add a note (optional)…"
          maxLength={500}
          className="mt-2 w-full text-xs bg-zinc-800 border border-zinc-700 rounded-lg p-2 text-zinc-300 placeholder:text-zinc-600 resize-none h-16 focus:outline-none focus:border-zinc-600 transition-colors"
        />
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

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
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 text-sm text-zinc-500">
        Loading span…
      </div>
    );
  }

  if (isError || !span) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-sm text-zinc-500">Span not found</p>
          <button
            onClick={() => router.push("/dashboard/traces")}
            className="mt-3 text-sm text-lime-400 hover:text-lime-300 transition-colors"
          >
            Back to Traces
          </button>
        </div>
      </div>
    );
  }

  const existingFeedback = span.tags?._feedback as string | undefined;

  return (
    <div className="flex flex-col min-h-screen bg-zinc-950">
      {/* Header */}
      <div className="bg-zinc-900 border-b border-zinc-800 px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/traces")}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-zinc-300">
                {span.id}
              </span>
              <StatusBadge status={span.status} />
            </div>
            <p className="text-xs text-zinc-500 mt-0.5">
              {span.provider} · {span.model} ·{" "}
              {span.started_at
                ? new Date(span.started_at).toLocaleString()
                : "—"}
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 space-y-4 max-w-5xl">
        {/* Metrics row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricChip
            icon={Clock}
            label="Latency"
            value={span.latency_ms !== null ? `${span.latency_ms} ms` : "—"}
          />
          <MetricChip
            icon={Zap}
            label="TTFT"
            value={span.ttft_ms !== null ? `${span.ttft_ms} ms` : "—"}
          />
          <MetricChip
            icon={DollarSign}
            label="Cost"
            value={
              span.cost_usd ? `$${parseFloat(span.cost_usd).toFixed(6)}` : "—"
            }
          />
          <MetricChip
            icon={AlertTriangle}
            label="Hallucination"
            value={
              span.hallucination_score
                ? parseFloat(span.hallucination_score).toFixed(2)
                : "—"
            }
          />
        </div>

        {/* Token counts */}
        <div className="flex gap-4 text-sm text-zinc-400 bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <span>
            <span className="text-zinc-600 text-xs">Input</span>{" "}
            <strong className="text-zinc-200">{span.input_tokens?.toLocaleString() ?? "—"}</strong>
          </span>
          <span className="text-zinc-700">·</span>
          <span>
            <span className="text-zinc-600 text-xs">Output</span>{" "}
            <strong className="text-zinc-200">{span.output_tokens?.toLocaleString() ?? "—"}</strong>
          </span>
          <span className="text-zinc-700">·</span>
          <span>
            <span className="text-zinc-600 text-xs">Total</span>{" "}
            <strong className="text-zinc-200">{span.total_tokens?.toLocaleString() ?? "—"}</strong>
          </span>
          {span.environment && (
            <>
              <span className="text-zinc-700">·</span>
              <span>
                <span className="text-zinc-600 text-xs">Env</span>{" "}
                <strong className="text-zinc-200">{span.environment}</strong>
              </span>
            </>
          )}
        </div>

        {/* Error details */}
        {span.error_type && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-sm">
            <p className="font-semibold text-red-400 mb-1">{span.error_type}</p>
            <p className="text-red-400/80 font-mono text-xs">{span.error_message}</p>
          </div>
        )}

        {/* Hallucination flags */}
        {span.hallucination_flags &&
          Object.keys(span.hallucination_flags).length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4">
              <p className="text-xs font-semibold text-amber-400 mb-2">
                Hallucination Signals
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(span.hallucination_flags).map(([k, v]) => (
                  <span
                    key={k}
                    className="px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded-full text-xs border border-amber-500/20"
                  >
                    {k}: {(v as number).toFixed(2)}
                  </span>
                ))}
              </div>
            </div>
          )}

        {/* Trace Gantt */}
        {span.siblings.length > 0 && (
          <GanttTimeline span={span} siblings={span.siblings} />
        )}

        {/* Payload viewers */}
        <JsonViewer data={span.request} label="Request Payload" />
        <JsonViewer data={span.response} label="Response Payload" />
        <JsonViewer
          data={
            span.tags && Object.keys(span.tags).length > 0 ? span.tags : null
          }
          label="Tags"
        />

        {/* Feedback */}
        {token && (
          <FeedbackPanel
            spanId={span.id}
            token={token}
            existingFeedback={existingFeedback}
          />
        )}
      </div>
    </div>
  );
}
