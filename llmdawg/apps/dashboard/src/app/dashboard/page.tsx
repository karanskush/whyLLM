"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  DollarSign,
  AlertTriangle,
  Clock,
  Zap,
  TrendingUp,
} from "lucide-react";
import { metrics, type MetricsSummary, type TimeWindow } from "@/lib/api";
import { CostLineChart } from "@/components/charts/cost-line-chart";
import { Topbar } from "@/components/layout/topbar";
import { useProject } from "@/hooks/useProject";
import { cn } from "@/lib/utils";

const TIME_WINDOWS: { label: string; value: TimeWindow }[] = [
  { label: "1h", value: "1h" },
  { label: "6h", value: "6h" },
  { label: "24h", value: "24h" },
  { label: "7d", value: "7d" },
  { label: "30d", value: "30d" },
];

interface LiveEvent {
  span_id: string;
  model: string;
  status: string;
  cost_usd?: number;
  latency_ms?: number;
}

interface KpiCardProps {
  title: string;
  value: string;
  icon: React.ElementType;
  iconColor: string;
  sub?: string;
}

function KpiCard({ title, value, icon: Icon, iconColor, sub }: KpiCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-500">{title}</span>
        <div className={cn("p-2 rounded-lg", iconColor)}>
          <Icon className="w-4 h-4 text-white" />
        </div>
      </div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-gray-400">{sub}</div>}
    </div>
  );
}

export default function OverviewPage() {
  const { data: session } = useSession();
  const [window, setWindow] = useState<TimeWindow>("24h");
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const { projectId } = useProject();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["metrics-summary", projectId, window, token],
    queryFn: () => metrics.summary(projectId!, window, token!),
    enabled: !!projectId && !!token,
    refetchInterval: 30_000,
    retry: false,
  });

  const { data: timeseries } = useQuery({
    queryKey: ["metrics-timeseries", projectId, window, token],
    queryFn: () => metrics.timeseries(projectId!, window, token!),
    enabled: !!projectId && !!token,
    refetchInterval: 60_000,
    retry: false,
  });

  // Live SSE feed — last 10 events
  useEffect(() => {
    if (!projectId || !token) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const es = new EventSource(
      `${apiUrl}/v1/projects/${projectId}/metrics/live?token=${encodeURIComponent(token)}`,
    );

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as LiveEvent;
        setLiveEvents((prev) => [data, ...prev].slice(0, 10));
      } catch {
        // ignore malformed events
      }
    };

    return () => es.close();
  }, [projectId, token]);

  const formatCost = (v?: number | null) =>
    v == null ? "—" : v < 0.001 ? `$${v.toFixed(6)}` : `$${v.toFixed(4)}`;

  const formatLatency = (v?: number | null) =>
    v == null ? "—" : v < 1000 ? `${Math.round(v)}ms` : `${(v / 1000).toFixed(2)}s`;

  return (
    <div>
      <Topbar title="Overview">
        <div className="flex gap-1">
          {TIME_WINDOWS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setWindow(value)}
              className={cn(
                "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                window === value
                  ? "bg-indigo-600 text-white"
                  : "text-gray-500 hover:bg-gray-100",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </Topbar>

      <div className="p-6 space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="Total Spans"
            value={summaryLoading ? "…" : (summary?.total_spans ?? 0).toLocaleString()}
            icon={Activity}
            iconColor="bg-indigo-500"
            sub={`Last ${window}`}
          />
          <KpiCard
            title="Total Cost"
            value={summaryLoading ? "…" : formatCost(summary?.total_cost_usd)}
            icon={DollarSign}
            iconColor="bg-emerald-500"
            sub={`Last ${window}`}
          />
          <KpiCard
            title="Error Rate"
            value={
              summaryLoading
                ? "…"
                : summary
                ? `${(summary.error_rate * 100).toFixed(1)}%`
                : "—"
            }
            icon={AlertTriangle}
            iconColor={
              summary && summary.error_rate > 0.05 ? "bg-red-500" : "bg-amber-500"
            }
            sub={`${summary?.error_count ?? 0} errors`}
          />
          <KpiCard
            title="P95 Latency"
            value={summaryLoading ? "…" : formatLatency(summary?.p95_latency_ms)}
            icon={Clock}
            iconColor="bg-violet-500"
            sub={`P50: ${formatLatency(summary?.p50_latency_ms)}`}
          />
        </div>

        {/* Cost over time chart */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-gray-400" />
            <h2 className="text-sm font-semibold text-gray-700">Cost over time</h2>
          </div>
          {timeseries ? (
            <CostLineChart
              series={timeseries.series}
              granularity={timeseries.granularity}
            />
          ) : (
            <div className="h-48 flex items-center justify-center text-sm text-gray-400">
              {summaryLoading ? "Loading…" : "No data"}
            </div>
          )}
        </div>

        {/* Live feed */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-semibold text-gray-700">Live feed</h2>
            <span className="ml-auto text-xs text-gray-400">Last 10 events</span>
          </div>
          {liveEvents.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">
              Waiting for events… Make an LLM call to see it here.
            </p>
          ) : (
            <div className="space-y-2">
              {liveEvents.map((ev, i) => (
                <div
                  key={`${ev.span_id}-${i}`}
                  className="flex items-center gap-3 py-2 border-b border-gray-50 last:border-0"
                >
                  <span
                    className={cn(
                      "w-2 h-2 rounded-full flex-shrink-0",
                      ev.status === "success" ? "bg-emerald-400" : "bg-red-400",
                    )}
                  />
                  <span className="text-sm font-medium text-gray-700 truncate flex-1">
                    {ev.model}
                  </span>
                  <span className="text-xs text-gray-400">{formatLatency(ev.latency_ms)}</span>
                  <span className="text-xs text-gray-500 font-mono">{formatCost(ev.cost_usd)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
