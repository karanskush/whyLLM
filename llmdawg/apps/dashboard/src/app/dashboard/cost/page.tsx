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

const BAR_COLORS = [
  "bg-lime-500", "bg-indigo-500", "bg-emerald-500", "bg-amber-500",
  "bg-rose-500", "bg-cyan-500", "bg-violet-500", "bg-pink-500",
];

function CostHeatmap({ items }: { items: CostBreakdownItem[] }) {
  const maxCost = useMemo(() => Math.max(...items.map((i) => i.cost_usd), 0.000001), [items]);

  if (items.length === 0) {
    return <p className="text-sm text-zinc-500 py-8 text-center">No data for this window.</p>;
  }

  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(items.length, 7)}, 1fr)` }}>
      {items.map((item) => {
        const opacity = Math.max(item.cost_usd / maxCost, 0.08);
        return (
          <div
            key={`${item.provider}-${item.model}`}
            className="rounded-lg p-3 flex flex-col gap-1 cursor-default"
            style={{ background: `rgba(163, 230, 53, ${opacity * 0.3})`, border: `1px solid rgba(163, 230, 53, ${opacity * 0.2})` }}
            title={`${item.model}: $${item.cost_usd.toFixed(6)}`}
          >
            <span className="text-xs font-medium text-zinc-300 truncate">{item.model}</span>
            <span className="text-xs text-zinc-500">${item.cost_usd.toFixed(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

function ModelBreakdown({ items }: { items: CostBreakdownItem[] }) {
  const sorted = useMemo(() => [...items].sort((a, b) => b.cost_usd - a.cost_usd), [items]);

  if (sorted.length === 0) {
    return <p className="text-sm text-zinc-500 py-8 text-center">No data for this window.</p>;
  }

  const maxCost = sorted[0].cost_usd || 0.000001;

  return (
    <div className="space-y-4">
      {sorted.map((item, idx) => (
        <div key={`${item.provider}-${item.model}`} className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-zinc-300 truncate max-w-[60%]">{item.model}</span>
            <span className="text-zinc-400 font-mono">${item.cost_usd.toFixed(5)}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
              <div
                className={cn("h-1.5 rounded-full transition-all", BAR_COLORS[idx % BAR_COLORS.length])}
                style={{ width: `${(item.cost_usd / maxCost) * 100}%` }}
              />
            </div>
            <span className="text-xs text-zinc-500 w-10 text-right">{item.pct_of_total.toFixed(1)}%</span>
          </div>
          <div className="text-xs text-zinc-600">
            {item.span_count.toLocaleString()} calls · {(item.input_tokens + item.output_tokens).toLocaleString()} tokens
          </div>
        </div>
      ))}
    </div>
  );
}

function TopUsersTable({ users, totalCost }: { users: { user_id: string; cost_usd: number }[]; totalCost: number }) {
  if (users.length === 0) {
    return <p className="text-sm text-zinc-500 py-4 text-center">No user data.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-zinc-600 border-b border-zinc-800">
          <th className="pb-2.5 font-medium">User ID</th>
          <th className="pb-2.5 font-medium text-right">Cost</th>
          <th className="pb-2.5 font-medium text-right">Share</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-zinc-800">
        {users.map((u) => (
          <tr key={u.user_id}>
            <td className="py-2.5 text-zinc-400 font-mono text-xs truncate max-w-[200px]">{u.user_id}</td>
            <td className="py-2.5 text-right font-mono text-xs text-zinc-300">${u.cost_usd.toFixed(5)}</td>
            <td className="py-2.5 text-right text-xs text-zinc-500">
              {totalCost > 0 ? ((u.cost_usd / totalCost) * 100).toFixed(1) : "0.0"}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function CostPage() {
  const { data: session } = useSession();
  const [window, setWindow] = useState<TimeWindow>("24h");
  const { projectId } = useProject();

  const token = session?.accessToken as string | undefined;

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
        <div className="flex gap-1 bg-zinc-800 rounded-lg p-0.5">
          {TIME_WINDOWS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setWindow(value)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                window === value ? "bg-zinc-700 text-white" : "text-zinc-400 hover:text-zinc-200",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </Topbar>

      <div className="p-6 space-y-5">
        {/* KPI cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Total Cost", value: isLoading ? "…" : `$${totalCost.toFixed(5)}`, icon: DollarSign, color: "bg-emerald-500/80", sub: `Last ${window}` },
            { label: "Models Used", value: isLoading ? "…" : String(data?.items.length ?? 0), icon: BarChart2, color: "bg-indigo-500/80", sub: "Distinct models" },
            { label: "Total Calls", value: isLoading ? "…" : (data?.items.reduce((s, i) => s + i.span_count, 0) ?? 0).toLocaleString(), icon: TrendingUp, color: "bg-violet-500/80", sub: "LLM requests" },
            { label: "Top Users", value: isLoading ? "…" : String(data?.top_users.length ?? 0), icon: Users, color: "bg-amber-500/80", sub: "With spend" },
          ].map(({ label, value, icon: Icon, color, sub }) => (
            <div key={label} className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{label}</span>
                <div className={cn("p-2 rounded-lg", color)}>
                  <Icon className="w-4 h-4 text-white" />
                </div>
              </div>
              <div className="text-2xl font-bold text-white">{value}</div>
              <div className="mt-1 text-xs text-zinc-500">{sub}</div>
            </div>
          ))}
        </div>

        {/* Model breakdown + top users */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
            <h2 className="text-sm font-semibold text-zinc-200 mb-5">Cost by model</h2>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => <div key={i} className="h-10 bg-zinc-800 rounded animate-pulse" />)}
              </div>
            ) : (
              <ModelBreakdown items={data?.items ?? []} />
            )}
          </div>

          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
            <h2 className="text-sm font-semibold text-zinc-200 mb-5">Top users by cost</h2>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => <div key={i} className="h-8 bg-zinc-800 rounded animate-pulse" />)}
              </div>
            ) : (
              <TopUsersTable users={data?.top_users ?? []} totalCost={totalCost} />
            )}
          </div>
        </div>

        {/* Heatmap */}
        <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-5">
          <h2 className="text-sm font-semibold text-zinc-200 mb-5">Cost heatmap by model</h2>
          {isLoading ? (
            <div className="h-24 bg-zinc-800 rounded animate-pulse" />
          ) : (
            <CostHeatmap items={data?.items ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}
