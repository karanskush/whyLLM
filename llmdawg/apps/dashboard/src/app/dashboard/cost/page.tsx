"use client";

import { useState, useMemo } from "react";
import { useSession } from "next-auth/react";
import { useQuery } from "@tanstack/react-query";
import { DollarSign, TrendingUp, Users, BarChart2 } from "lucide-react";
import { cost, type CostBreakdownItem, type TimeWindow } from "@/lib/api";
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

// ── Color palette for providers / models ──────────────────────────────────────

const COLORS = [
  "bg-indigo-500",
  "bg-violet-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-cyan-500",
  "bg-teal-500",
  "bg-pink-500",
];

// ── Cost heatmap (7-row × N-col CSS grid) ────────────────────────────────────

function CostHeatmap({ items }: { items: CostBreakdownItem[] }) {
  const maxCost = useMemo(
    () => Math.max(...items.map((i) => i.cost_usd), 0.000001),
    [items],
  );

  if (items.length === 0) {
    return (
      <p className="text-sm text-gray-400 py-8 text-center">No data for this window.</p>
    );
  }

  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(items.length, 7)}, 1fr)` }}>
      {items.map((item) => {
        const opacity = Math.max(item.cost_usd / maxCost, 0.08);
        return (
          <div
            key={`${item.provider}-${item.model}`}
            className="rounded-lg p-3 flex flex-col gap-1 cursor-default"
            style={{ background: `rgba(99, 102, 241, ${opacity})` }}
            title={`${item.model}: $${item.cost_usd.toFixed(6)}`}
          >
            <span className="text-xs font-medium text-gray-700 truncate">{item.model}</span>
            <span className="text-xs text-gray-500">${item.cost_usd.toFixed(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Model breakdown bar chart (pure CSS) ─────────────────────────────────────

function ModelBreakdown({ items }: { items: CostBreakdownItem[] }) {
  const sorted = useMemo(
    () => [...items].sort((a, b) => b.cost_usd - a.cost_usd),
    [items],
  );

  if (sorted.length === 0) {
    return <p className="text-sm text-gray-400 py-8 text-center">No data for this window.</p>;
  }

  const maxCost = sorted[0].cost_usd || 0.000001;

  return (
    <div className="space-y-3">
      {sorted.map((item, idx) => (
        <div key={`${item.provider}-${item.model}`} className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-gray-700 truncate max-w-[60%]">{item.model}</span>
            <span className="text-gray-500 font-mono">${item.cost_usd.toFixed(5)}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
              <div
                className={cn("h-2 rounded-full transition-all", COLORS[idx % COLORS.length])}
                style={{ width: `${(item.cost_usd / maxCost) * 100}%` }}
              />
            </div>
            <span className="text-xs text-gray-400 w-10 text-right">
              {item.pct_of_total.toFixed(1)}%
            </span>
          </div>
          <div className="text-xs text-gray-400">
            {item.span_count.toLocaleString()} calls ·{" "}
            {(item.input_tokens + item.output_tokens).toLocaleString()} tokens
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Top users table ───────────────────────────────────────────────────────────

function TopUsersTable({
  users,
  totalCost,
}: {
  users: { user_id: string; cost_usd: number }[];
  totalCost: number;
}) {
  if (users.length === 0) {
    return <p className="text-sm text-gray-400 py-4 text-center">No user data.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
          <th className="pb-2 font-medium">User ID</th>
          <th className="pb-2 font-medium text-right">Cost</th>
          <th className="pb-2 font-medium text-right">Share</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {users.map((u) => (
          <tr key={u.user_id}>
            <td className="py-2 text-gray-700 font-mono text-xs truncate max-w-[200px]">
              {u.user_id}
            </td>
            <td className="py-2 text-right font-mono text-xs text-gray-700">
              ${u.cost_usd.toFixed(5)}
            </td>
            <td className="py-2 text-right text-xs text-gray-400">
              {totalCost > 0 ? ((u.cost_usd / totalCost) * 100).toFixed(1) : "0.0"}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CostPage() {
  const { data: session } = useSession();
  const [window, setWindow] = useState<TimeWindow>("24h");
  const { projectId } = useProject();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  const { data, isLoading } = useQuery({
    queryKey: ["cost-breakdown", projectId, window, token],
    queryFn: () => cost.breakdown(projectId!, window, token!),
    enabled: !!projectId && !!token,
    refetchInterval: 60_000,
    retry: false,
  });

  const totalCost = data?.total_cost_usd ?? 0;

  return (
    <div>
      <Topbar title="Cost Analytics">
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
        {/* Summary KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-500">Total Cost</span>
              <div className="p-2 rounded-lg bg-emerald-500">
                <DollarSign className="w-4 h-4 text-white" />
              </div>
            </div>
            <div className="text-2xl font-bold text-gray-900">
              {isLoading ? "…" : `$${totalCost.toFixed(5)}`}
            </div>
            <div className="mt-1 text-xs text-gray-400">Last {window}</div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-500">Models Used</span>
              <div className="p-2 rounded-lg bg-indigo-500">
                <BarChart2 className="w-4 h-4 text-white" />
              </div>
            </div>
            <div className="text-2xl font-bold text-gray-900">
              {isLoading ? "…" : (data?.items.length ?? 0)}
            </div>
            <div className="mt-1 text-xs text-gray-400">Distinct models</div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-500">Total Calls</span>
              <div className="p-2 rounded-lg bg-violet-500">
                <TrendingUp className="w-4 h-4 text-white" />
              </div>
            </div>
            <div className="text-2xl font-bold text-gray-900">
              {isLoading
                ? "…"
                : (data?.items.reduce((s, i) => s + i.span_count, 0) ?? 0).toLocaleString()}
            </div>
            <div className="mt-1 text-xs text-gray-400">LLM requests</div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-500">Top Users</span>
              <div className="p-2 rounded-lg bg-amber-500">
                <Users className="w-4 h-4 text-white" />
              </div>
            </div>
            <div className="text-2xl font-bold text-gray-900">
              {isLoading ? "…" : (data?.top_users.length ?? 0)}
            </div>
            <div className="mt-1 text-xs text-gray-400">With spend</div>
          </div>
        </div>

        {/* Two-column layout: model breakdown + top users */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">Cost by model</h2>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
                ))}
              </div>
            ) : (
              <ModelBreakdown items={data?.items ?? []} />
            )}
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">Top users by cost</h2>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-8 bg-gray-100 rounded animate-pulse" />
                ))}
              </div>
            ) : (
              <TopUsersTable users={data?.top_users ?? []} totalCost={totalCost} />
            )}
          </div>
        </div>

        {/* Cost heatmap */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Cost heatmap by model</h2>
          {isLoading ? (
            <div className="h-24 bg-gray-100 rounded animate-pulse" />
          ) : (
            <CostHeatmap items={data?.items ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}
