"use client";

import { useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Check,
  DollarSign,
  Gauge,
  Info,
  Lightbulb,
  RotateCcw,
} from "lucide-react";
import {
  insights as insightsApi,
  type Insight,
  type InsightSeverity,
  type InsightStatus,
  type InsightType,
} from "@/lib/api";
import { Topbar } from "@/components/layout/topbar";
import { useProject } from "@/hooks/useProject";
import { cn } from "@/lib/utils";

const STATUS_FILTERS: { label: string; value: InsightStatus | "all" }[] = [
  { label: "Open", value: "open" },
  { label: "Acknowledged", value: "acknowledged" },
  { label: "Resolved", value: "resolved" },
  { label: "All", value: "all" },
];

const TYPE_META: Record<InsightType, { label: string; icon: typeof DollarSign }> = {
  cost_forecast: { label: "Cost forecast", icon: DollarSign },
  rate_limit_eta: { label: "Rate limit", icon: Gauge },
  model_drift: { label: "Model drift", icon: Activity },
};

const SEVERITY_META: Record<
  InsightSeverity,
  { label: string; icon: typeof Info; text: string; bg: string; border: string; dot: string }
> = {
  critical: {
    label: "Critical",
    icon: AlertTriangle,
    text: "text-rose-400",
    bg: "bg-rose-500/10",
    border: "border-rose-500/30",
    dot: "bg-rose-500",
  },
  warning: {
    label: "Warning",
    icon: AlertCircle,
    text: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    dot: "bg-amber-500",
  },
  info: {
    label: "Info",
    icon: Info,
    text: "text-sky-400",
    bg: "bg-sky-500/10",
    border: "border-sky-500/30",
    dot: "bg-sky-500",
  },
};

const SEVERITY_RANK: Record<InsightSeverity, number> = { critical: 0, warning: 1, info: 2 };

/** snake_case → "Title Case" for detail keys. */
function humanize(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\busd\b/i, "USD")
    .replace(/\bpct\b/i, "%")
    .replace(/\beta\b/i, "ETA")
    .replace(/^\w/, (c) => c.toUpperCase());
}

/** Render a scalar detail value with light unit-aware formatting. */
function formatValue(key: string, value: unknown): string {
  if (typeof value === "number") {
    if (key.includes("usd")) return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    if (key.includes("pct") || key.includes("percent")) return `${value}%`;
    return value.toLocaleString();
  }
  return String(value);
}

function DetailChips({ detail }: { detail: Record<string, unknown> }) {
  const scalars = Object.entries(detail).filter(
    ([, v]) => v !== null && (typeof v === "number" || typeof v === "string"),
  );
  if (scalars.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      {scalars.map(([k, v]) => (
        <span
          key={k}
          className="inline-flex items-center gap-1.5 rounded-md bg-zinc-800/80 px-2 py-1 text-[11px]"
        >
          <span className="text-zinc-500">{humanize(k)}</span>
          <span className="font-mono text-zinc-300">{formatValue(k, v)}</span>
        </span>
      ))}
    </div>
  );
}

function InsightCard({
  insight,
  onUpdate,
  pending,
}: {
  insight: Insight;
  onUpdate: (id: string, status: InsightStatus) => void;
  pending: boolean;
}) {
  const sev = SEVERITY_META[insight.severity];
  const type = TYPE_META[insight.type];
  const SevIcon = sev.icon;
  const TypeIcon = type.icon;

  return (
    <div className={cn("rounded-xl border p-5", sev.bg, sev.border)}>
      <div className="flex items-start gap-4">
        <div className={cn("mt-0.5 rounded-lg p-2", sev.bg)}>
          <SevIcon className={cn("h-5 w-5", sev.text)} />
        </div>

        <div className="min-w-0 flex-1">
          {/* Meta row */}
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <span className={cn("font-semibold uppercase tracking-wider", sev.text)}>
              {sev.label}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              <TypeIcon className="h-3 w-3" />
              {type.label}
            </span>
            {insight.confidence !== null && (
              <span className="text-zinc-500">
                {Math.round(insight.confidence * 100)}% confidence
              </span>
            )}
            {insight.status !== "open" && (
              <span className="rounded-md bg-zinc-800 px-1.5 py-0.5 text-zinc-500 capitalize">
                {insight.status}
              </span>
            )}
          </div>

          <h3 className="mt-1.5 text-sm font-semibold text-white">{insight.title}</h3>
          <p className="mt-1 text-sm leading-relaxed text-zinc-400">{insight.summary}</p>

          {Array.isArray(insight.detail.shifts) && (
            <ul className="mt-2 space-y-0.5">
              {(insight.detail.shifts as string[]).map((s, i) => (
                <li key={i} className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <span className={cn("h-1 w-1 rounded-full", sev.dot)} />
                  {s}
                </li>
              ))}
            </ul>
          )}

          <DetailChips detail={insight.detail} />

          {insight.predicted_for && (
            <p className="mt-3 text-xs text-zinc-500">
              Predicted for{" "}
              <span className="text-zinc-300">
                {new Date(insight.predicted_for).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </span>
            </p>
          )}

          {/* Actions */}
          <div className="mt-4 flex items-center gap-2">
            {insight.status !== "resolved" && (
              <button
                disabled={pending}
                onClick={() => onUpdate(insight.id, "resolved")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-lime-500 px-2.5 py-1.5 text-xs font-medium text-black transition-colors hover:bg-lime-400 disabled:opacity-50"
              >
                <Check className="h-3.5 w-3.5" />
                Resolve
              </button>
            )}
            {insight.status === "open" && (
              <button
                disabled={pending}
                onClick={() => onUpdate(insight.id, "acknowledged")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-2.5 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700 disabled:opacity-50"
              >
                Acknowledge
              </button>
            )}
            {insight.status !== "open" && (
              <button
                disabled={pending}
                onClick={() => onUpdate(insight.id, "open")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-2.5 py-1.5 text-xs font-medium text-zinc-400 transition-colors hover:bg-zinc-700 disabled:opacity-50"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reopen
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function InsightsPage() {
  const { data: session } = useSession();
  const { projectId } = useProject();
  const [status, setStatus] = useState<InsightStatus | "all">("open");
  const queryClient = useQueryClient();

  const token = session?.accessToken as string | undefined;

  const { data, isLoading } = useQuery({
    queryKey: ["insights", projectId, status, token],
    queryFn: () => insightsApi.list(projectId!, { status }, token!),
    enabled: !!projectId && !!token,
    refetchInterval: 60_000,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: ({ id, status: next }: { id: string; status: InsightStatus }) =>
      insightsApi.updateStatus(id, next, token!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["insights", projectId] }),
  });

  const list = useMemo(() => {
    const items = data?.insights ?? [];
    return [...items].sort(
      (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity],
    );
  }, [data]);

  const counts = useMemo(() => {
    const c = { critical: 0, warning: 0, info: 0 };
    for (const i of data?.insights ?? []) c[i.severity]++;
    return c;
  }, [data]);

  return (
    <div>
      <Topbar title="Insights">
        <div className="flex gap-1 rounded-lg bg-zinc-800 p-0.5">
          {STATUS_FILTERS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setStatus(value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                status === value
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-zinc-200",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </Topbar>

      <div className="space-y-5 p-6">
        {/* Severity KPI row */}
        <div className="grid grid-cols-3 gap-4">
          {(["critical", "warning", "info"] as InsightSeverity[]).map((s) => {
            const meta = SEVERITY_META[s];
            const Icon = meta.icon;
            return (
              <div key={s} className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wider text-zinc-400">
                    {meta.label}
                  </span>
                  <div className={cn("rounded-lg p-2", meta.bg)}>
                    <Icon className={cn("h-4 w-4", meta.text)} />
                  </div>
                </div>
                <div className="text-2xl font-bold text-white">
                  {isLoading ? "…" : counts[s]}
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  {status === "all" ? "All time" : `${status} insights`}
                </div>
              </div>
            );
          })}
        </div>

        {/* Insight list */}
        <div className="space-y-3">
          {isLoading ? (
            [1, 2, 3].map((i) => (
              <div key={i} className="h-32 animate-pulse rounded-xl bg-zinc-900" />
            ))
          ) : list.length === 0 ? (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 py-16 text-center">
              <Lightbulb className="mx-auto mb-3 h-8 w-8 text-zinc-700" />
              <p className="text-sm font-medium text-zinc-300">No {status} insights</p>
              <p className="mx-auto mt-1 max-w-sm text-xs text-zinc-500">
                The prediction engine sweeps your traffic every few minutes and
                surfaces cost forecasts, rate-limit ETAs, and model drift here.
              </p>
            </div>
          ) : (
            list.map((insight) => (
              <InsightCard
                key={insight.id}
                insight={insight}
                pending={mutation.isPending}
                onUpdate={(id, next) => mutation.mutate({ id, status: next })}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
