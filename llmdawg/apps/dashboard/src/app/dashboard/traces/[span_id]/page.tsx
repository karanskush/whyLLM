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
      ? "bg-green-100 text-green-700"
      : status === "error"
        ? "bg-red-100 text-red-700"
        : "bg-yellow-100 text-yellow-700";
  return (
    <span className={cn("px-2 py-1 rounded-full text-xs font-medium", color)}>
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
    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
      <Icon className="w-4 h-4 text-gray-400" />
      <div>
        <div className="text-xs text-gray-400">{label}</div>
        <div className="text-sm font-semibold text-gray-800">{value}</div>
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
    <div className="border border-gray-100 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 text-sm font-medium text-gray-700"
      >
        <span>{label}</span>
        {open ? (
          <ChevronDown className="w-4 h-4" />
        ) : (
          <ChevronRight className="w-4 h-4" />
        )}
      </button>
      {open && (
        <pre className="p-4 text-xs font-mono text-gray-600 bg-white overflow-x-auto max-h-96">
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
    <div className="bg-white border border-gray-100 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
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
                <div className="w-24 text-xs text-gray-400 truncate text-right flex-shrink-0">
                  {s.model.split("-").slice(-2).join("-")}
                </div>
                <div className="flex-1 relative h-6 bg-gray-100 rounded">
                  <div
                    className={cn(
                      "absolute top-1 h-4 rounded",
                      isCurrent
                        ? "bg-indigo-500"
                        : s.status === "error"
                          ? "bg-red-400"
                          : "bg-indigo-200",
                    )}
                    style={{
                      left: `${Math.min(leftPct, 99)}%`,
                      width: `${Math.max(Math.min(widthPct, 100 - leftPct), 0.5)}%`,
                    }}
                  />
                </div>
                <div className="w-16 text-xs text-gray-400 flex-shrink-0">
                  {s.latency_ms !== null ? `${s.latency_ms}ms` : "—"}
                </div>
              </div>
            );
          })}
      </div>
      <div className="flex justify-between mt-2 text-xs text-gray-300">
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
    <div className="bg-white border border-gray-100 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Feedback</h3>
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
                ? "bg-indigo-600 text-white border-indigo-600"
                : "bg-white text-gray-600 border-gray-200 hover:border-indigo-300 hover:text-indigo-600",
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
          className="mt-2 w-full text-xs border border-gray-200 rounded p-2 resize-none h-16 focus:outline-none focus:border-indigo-400"
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
      <div className="flex items-center justify-center min-h-screen text-sm text-gray-400">
        Loading span…
      </div>
    );
  }

  if (isError || !span) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-sm text-gray-500">Span not found</p>
          <button
            onClick={() => router.push("/dashboard/traces")}
            className="mt-3 text-sm text-indigo-600 hover:underline"
          >
            Back to Traces
          </button>
        </div>
      </div>
    );
  }

  const existingFeedback = span.tags?._feedback as string | undefined;

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/traces")}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-gray-800">
                {span.id}
              </span>
              <StatusBadge status={span.status} />
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
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
        <div className="flex gap-4 text-sm text-gray-600 bg-white border border-gray-100 rounded-xl p-4">
          <span>
            <span className="text-gray-400 text-xs">Input</span>{" "}
            <strong>{span.input_tokens?.toLocaleString() ?? "—"}</strong>
          </span>
          <span className="text-gray-300">·</span>
          <span>
            <span className="text-gray-400 text-xs">Output</span>{" "}
            <strong>{span.output_tokens?.toLocaleString() ?? "—"}</strong>
          </span>
          <span className="text-gray-300">·</span>
          <span>
            <span className="text-gray-400 text-xs">Total</span>{" "}
            <strong>{span.total_tokens?.toLocaleString() ?? "—"}</strong>
          </span>
          {span.environment && (
            <>
              <span className="text-gray-300">·</span>
              <span>
                <span className="text-gray-400 text-xs">Env</span>{" "}
                <strong>{span.environment}</strong>
              </span>
            </>
          )}
        </div>

        {/* Error details */}
        {span.error_type && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm">
            <p className="font-semibold text-red-700 mb-1">{span.error_type}</p>
            <p className="text-red-600 font-mono text-xs">{span.error_message}</p>
          </div>
        )}

        {/* Hallucination flags */}
        {span.hallucination_flags &&
          Object.keys(span.hallucination_flags).length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
              <p className="text-xs font-semibold text-yellow-700 mb-2">
                Hallucination Signals
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(span.hallucination_flags).map(([k, v]) => (
                  <span
                    key={k}
                    className="px-2 py-0.5 bg-yellow-100 text-yellow-800 rounded text-xs"
                  >
                    {k}: {(v as number).toFixed(2)}
                  </span>
                ))}
              </div>
            </div>
          )}

        {/* Trace Gantt (only when there are siblings) */}
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
