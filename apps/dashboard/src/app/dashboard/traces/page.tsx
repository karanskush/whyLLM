"use client";

import { Fragment, useCallback, useMemo, useState, Suspense } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Search, X, ChevronDown, ChevronRight } from "lucide-react";
import { spans, type SpanListItem, type SpanFilters } from "@/lib/api";
import { Topbar } from "@/components/layout/topbar";
import { useProject } from "@/hooks/useProject";
import { cn } from "@/lib/utils";

const LABEL =
  "text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500";

// ── Atoms ─────────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const color =
    status === "success"
      ? "bg-lime-400"
      : status === "error"
        ? "bg-red-400"
        : "bg-amber-400";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-zinc-300">
      <span className={cn("w-1.5 h-1.5 rounded-full", color)} />
      <span className="capitalize">{status}</span>
    </span>
  );
}

function LatencyText({
  ms,
  muted = false,
}: {
  ms: number | null;
  muted?: boolean;
}) {
  if (ms === null) return <span className="text-xs text-zinc-600">—</span>;
  const tone =
    ms > 5000
      ? "text-red-300"
      : ms > 2000
        ? "text-amber-300"
        : muted
          ? "text-zinc-400"
          : "text-zinc-200";
  return (
    <span className={cn("text-xs tabular-nums font-mono", tone)}>
      {ms.toLocaleString()}ms
    </span>
  );
}

function HallucinationText({
  score,
  muted = false,
}: {
  score: string | null;
  muted?: boolean;
}) {
  if (!score) return <span className="text-zinc-600 text-xs">—</span>;
  const v = parseFloat(score);
  const tone =
    v > 0.5
      ? "text-red-300"
      : v > 0.3
        ? "text-amber-300"
        : muted
          ? "text-zinc-500"
          : "text-zinc-400";
  return (
    <span className={cn("text-xs font-mono tabular-nums", tone)}>
      {v.toFixed(2)}
    </span>
  );
}

function formatTime(v: string | null): string {
  if (!v) return "—";
  return new Date(v).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ── Filters ───────────────────────────────────────────────────────────────────

function useTracesFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const filters: SpanFilters = {
    model: searchParams.get("model") || undefined,
    provider: searchParams.get("provider") || undefined,
    status: searchParams.get("status") || undefined,
    environment: searchParams.get("environment") || undefined,
    has_hallucination:
      searchParams.get("has_hallucination") === "true"
        ? true
        : searchParams.get("has_hallucination") === "false"
          ? false
          : undefined,
    limit: 50,
  };

  const setFilter = useCallback(
    (key: keyof SpanFilters, value: string | boolean | undefined) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value === undefined || value === "") params.delete(key);
      else params.set(key, String(value));
      router.push(`${pathname}?${params.toString()}`);
    },
    [router, pathname, searchParams],
  );

  const clearFilters = useCallback(() => router.push(pathname), [router, pathname]);

  const activeCount = Object.values(filters).filter(
    (v) => v !== undefined && v !== 50,
  ).length;

  return { filters, setFilter, clearFilters, activeCount };
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const active = value !== "";
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "appearance-none pl-2.5 pr-6 h-7 text-[12px] rounded-md border bg-transparent cursor-pointer transition-colors focus:outline-none",
          active
            ? "border-lime-400/50 text-lime-300"
            : "border-zinc-800 text-zinc-400 hover:border-zinc-700",
        )}
      >
        <option value="">{label}</option>
        {options.slice(1).map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-500 pointer-events-none" />
    </div>
  );
}

function ModelFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative flex items-center">
      <Search className="absolute left-2 w-3 h-3 text-zinc-500" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Model"
        className="pl-6 pr-2.5 h-7 text-[12px] rounded-md border border-zinc-800 bg-transparent text-zinc-200 placeholder:text-zinc-600 w-36 focus:outline-none focus:border-zinc-700 transition-colors"
      />
    </div>
  );
}

function FilterBar({
  filters,
  setFilter,
  clearFilters,
  activeCount,
}: {
  filters: SpanFilters;
  setFilter: (k: keyof SpanFilters, v: string | boolean | undefined) => void;
  clearFilters: () => void;
  activeCount: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <FilterSelect
        label="Status"
        value={filters.status || ""}
        options={["", "success", "error", "streaming", "cancelled"]}
        onChange={(v) => setFilter("status", v || undefined)}
      />
      <FilterSelect
        label="Provider"
        value={filters.provider || ""}
        options={["", "openai", "anthropic", "google", "cohere", "azure"]}
        onChange={(v) => setFilter("provider", v || undefined)}
      />
      <FilterSelect
        label="Env"
        value={filters.environment || ""}
        options={["", "production", "staging", "development"]}
        onChange={(v) => setFilter("environment", v || undefined)}
      />
      <FilterSelect
        label="Hallucination"
        value={
          filters.has_hallucination === true
            ? "true"
            : filters.has_hallucination === false
              ? "false"
              : ""
        }
        options={["", "true", "false"]}
        onChange={(v) =>
          setFilter(
            "has_hallucination",
            v === "true" ? true : v === "false" ? false : undefined,
          )
        }
      />
      <ModelFilter
        value={filters.model || ""}
        onChange={(v) => setFilter("model", v || undefined)}
      />
      {activeCount > 0 && (
        <button
          onClick={clearFilters}
          className="inline-flex items-center gap-1 text-[12px] text-zinc-500 hover:text-zinc-200 px-2 h-7 rounded-md border border-zinc-800 hover:border-zinc-700 transition-colors"
        >
          <X className="w-3 h-3" />
          Clear ({activeCount})
        </button>
      )}
    </div>
  );
}

// ── Grouping ──────────────────────────────────────────────────────────────────

// Each group collects all spans that hit the same logical endpoint
// (e.g. "chat.completions", "embeddings", "messages"). The proxy sets
// span.name from X-whyllm-Name or derives it from the upstream URL path.
type EndpointGroup = {
  key: string;            // "<provider>:<name>" or "__unclassified__"
  endpoint: string;       // display label, e.g. "chat.completions"
  provider: string | null;
  spans: SpanListItem[];
};

function groupByEndpoint(items: SpanListItem[]): EndpointGroup[] {
  const groups: EndpointGroup[] = [];
  const idx = new Map<string, number>();
  for (const s of items) {
    const endpoint = (s.name || "").trim();
    if (!endpoint) {
      groups.push({
        key: `span:${s.id}`,
        endpoint: "unclassified",
        provider: s.provider,
        spans: [s],
      });
      continue;
    }
    const key = `${s.provider}:${endpoint}`;
    const existing = idx.get(key);
    if (existing === undefined) {
      idx.set(key, groups.length);
      groups.push({ key, endpoint, provider: s.provider, spans: [s] });
    } else {
      groups[existing].spans.push(s);
    }
  }
  // Newest call first within each group — matches the list-level ordering.
  for (const g of groups) {
    g.spans.sort((a, b) => {
      const ta = a.started_at ? Date.parse(a.started_at) : 0;
      const tb = b.started_at ? Date.parse(b.started_at) : 0;
      return tb - ta;
    });
  }
  // Groups themselves ordered by most-recent activity (newest endpoint first).
  groups.sort((a, b) => {
    const ta = a.spans[0]?.started_at
      ? Date.parse(a.spans[0].started_at as string)
      : 0;
    const tb = b.spans[0]?.started_at
      ? Date.parse(b.spans[0].started_at as string)
      : 0;
    return tb - ta;
  });
  return groups;
}

type Aggregate = {
  lastSeenAt: string | null;
  status: string;
  model: string | null;
  modelCount: number;
  provider: string | null;
  latencyP50: number | null;  // median — meaningful across arbitrary call windows
  costUsd: number;            // sum — "how much did this endpoint cost me?"
  totalTokens: number;
  inputTokens: number;
  outputTokens: number;
  hallucinationMax: string | null;
  environment: string;
};

function median(nums: number[]): number | null {
  if (nums.length === 0) return null;
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? Math.round((sorted[mid - 1] + sorted[mid]) / 2)
    : sorted[mid];
}

function aggregate(spans: SpanListItem[]): Aggregate {
  const statusOrder: Record<string, number> = {
    error: 3,
    cancelled: 2,
    streaming: 1,
    success: 0,
  };
  let worstStatus = "success";
  let lastSeenAt: string | null = null;
  const latencies: number[] = [];
  let cost = 0;
  let totalTok = 0;
  let inputTok = 0;
  let outputTok = 0;
  let hallMax: number | null = null;
  const models = new Set<string>();
  const providers = new Set<string>();

  for (const s of spans) {
    // Group row shows the most recent hit — "last seen" — since groups may
    // span hours or days of activity against the same endpoint.
    if (s.started_at && (!lastSeenAt || s.started_at > lastSeenAt)) {
      lastSeenAt = s.started_at;
    }
    if ((statusOrder[s.status] ?? 0) > (statusOrder[worstStatus] ?? 0)) {
      worstStatus = s.status;
    }
    if (s.latency_ms !== null) latencies.push(s.latency_ms);
    if (s.cost_usd) cost += parseFloat(s.cost_usd);
    totalTok += s.total_tokens ?? 0;
    inputTok += s.input_tokens ?? 0;
    outputTok += s.output_tokens ?? 0;
    if (s.hallucination_score) {
      const v = parseFloat(s.hallucination_score);
      if (hallMax === null || v > hallMax) hallMax = v;
    }
    models.add(s.model);
    providers.add(s.provider);
  }

  return {
    lastSeenAt,
    status: worstStatus,
    model: models.size === 1 ? [...models][0] : null,
    modelCount: models.size,
    provider: providers.size === 1 ? [...providers][0] : null,
    latencyP50: median(latencies),
    costUsd: cost,
    totalTokens: totalTok,
    inputTokens: inputTok,
    outputTokens: outputTok,
    hallucinationMax: hallMax !== null ? hallMax.toString() : null,
    environment: spans[0].environment,
  };
}

// ── Summary strip ─────────────────────────────────────────────────────────────

function SummaryStrip({
  items,
  endpointCount,
}: {
  items: SpanListItem[];
  endpointCount: number;
}) {
  const stats = useMemo(() => {
    if (items.length === 0) return null;
    const totalCost = items.reduce(
      (s, i) => s + (i.cost_usd ? parseFloat(i.cost_usd) : 0),
      0,
    );
    const totalTokens = items.reduce((s, i) => s + (i.total_tokens ?? 0), 0);
    const errors = items.filter((i) => i.status === "error").length;
    const lat = items
      .map((i) => i.latency_ms)
      .filter((n): n is number => n !== null);
    const sorted = lat.length > 0 ? [...lat].sort((a, b) => a - b) : null;
    const p50 = sorted ? sorted[Math.floor(sorted.length / 2)] : null;
    const p95 = sorted ? sorted[Math.floor(sorted.length * 0.95)] : null;
    return { totalCost, totalTokens, errors, p50, p95, shown: items.length };
  }, [items]);

  if (!stats) return null;

  const cells = [
    { label: "Endpoints", value: endpointCount.toLocaleString() },
    { label: "Calls", value: stats.shown.toLocaleString() },
    { label: "p50", value: stats.p50 !== null ? `${stats.p50}ms` : "—" },
    { label: "p95", value: stats.p95 !== null ? `${stats.p95}ms` : "—" },
    { label: "Tokens", value: stats.totalTokens.toLocaleString() },
    { label: "Cost", value: `$${stats.totalCost.toFixed(4)}` },
    {
      label: "Errors",
      value: stats.errors.toString(),
      danger: stats.errors > 0,
    },
  ];

  return (
    <div className="flex items-stretch border border-zinc-800/70 rounded-lg bg-zinc-900/30 divide-x divide-zinc-800/70 overflow-x-auto">
      {cells.map((c) => (
        <div key={c.label} className="flex-1 min-w-[82px] px-4 py-2.5">
          <div className={LABEL}>{c.label}</div>
          <div
            className={cn(
              "mt-0.5 text-[15px] font-medium tabular-nums tracking-tight",
              c.danger ? "text-red-300" : "text-zinc-100",
            )}
          >
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Table rows ────────────────────────────────────────────────────────────────

const HEADERS = [
  "Last",
  "Status",
  "Endpoint",
  "p50",
  "Cost",
  "Tokens",
  "Hall.",
  "Env",
  "Calls",
];

function GroupRow({
  group,
  expanded,
  onToggle,
  onOpenSpan,
}: {
  group: EndpointGroup;
  expanded: boolean;
  onToggle: () => void;
  onOpenSpan: (id: string) => void;
}) {
  const isMulti = group.spans.length > 1;
  const agg = useMemo(() => aggregate(group.spans), [group.spans]);

  const onClick = () => {
    if (isMulti) onToggle();
    else onOpenSpan(group.spans[0].id);
  };

  return (
    <tr
      onClick={onClick}
      className={cn(
        "border-b border-zinc-800/40 last:border-b-0 cursor-pointer transition-colors",
        isMulti && expanded
          ? "bg-zinc-900/50 hover:bg-zinc-900/60"
          : "hover:bg-zinc-900/60",
      )}
    >
      {/* Last seen + chevron */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <div className="flex items-center gap-2">
          {isMulti ? (
            <ChevronRight
              className={cn(
                "w-3 h-3 text-zinc-500 transition-transform shrink-0",
                expanded && "rotate-90",
              )}
            />
          ) : (
            <span className="w-3 h-3 shrink-0" />
          )}
          <span className="text-zinc-400 text-xs tabular-nums font-mono">
            {formatTime(agg.lastSeenAt)}
          </span>
        </div>
      </td>

      {/* Status */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <StatusDot status={agg.status} />
      </td>

      {/* Endpoint + model subtitle */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <div className="flex flex-col min-w-0">
          <span className="text-[13.5px] text-zinc-50 truncate max-w-[280px] font-medium tracking-tight">
            {group.endpoint}
          </span>
          <span className="text-[10.5px] text-zinc-500 truncate max-w-[280px]">
            {agg.model ?? `${agg.modelCount} models`}
            {agg.provider && (
              <>
                {" · "}
                <span className="capitalize">{agg.provider}</span>
              </>
            )}
          </span>
        </div>
      </td>

      {/* p50 latency */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <LatencyText ms={agg.latencyP50} />
      </td>

      {/* Cost (sum) */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <span className="text-xs font-mono text-zinc-300 tabular-nums">
          {agg.costUsd > 0 ? `$${agg.costUsd.toFixed(6)}` : "—"}
        </span>
      </td>

      {/* Tokens (sum) */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <div className="text-xs tabular-nums">
          <div className="text-zinc-200 font-mono">
            {agg.totalTokens > 0 ? agg.totalTokens.toLocaleString() : "—"}
          </div>
          {agg.inputTokens > 0 && agg.outputTokens > 0 && (
            <div className="text-[10px] text-zinc-500 font-mono">
              {agg.inputTokens.toLocaleString()} ·{" "}
              {agg.outputTokens.toLocaleString()}
            </div>
          )}
        </div>
      </td>

      {/* Hallucination (max) */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <HallucinationText score={agg.hallucinationMax} />
      </td>

      {/* Env */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <span className="text-[11px] text-zinc-500">{agg.environment}</span>
      </td>

      {/* Call count */}
      <td className="px-4 py-2.5 whitespace-nowrap">
        <span
          className={cn(
            "inline-flex items-center justify-center min-w-[28px] px-1.5 h-[20px] rounded-full tabular-nums text-[11px] font-medium",
            isMulti
              ? "bg-zinc-800/80 text-zinc-100"
              : "text-zinc-500",
          )}
        >
          {group.spans.length}
        </span>
      </td>
    </tr>
  );
}

function ChildRow({
  span,
  onOpen,
}: {
  span: SpanListItem;
  onOpen: (id: string) => void;
}) {
  return (
    <tr
      onClick={(e) => {
        e.stopPropagation();
        onOpen(span.id);
      }}
      className="border-b border-zinc-800/30 last:border-b-0 bg-zinc-900/20 hover:bg-zinc-900/40 cursor-pointer transition-colors"
    >
      {/* Time + rail */}
      <td className="pl-10 pr-4 py-2 whitespace-nowrap relative">
        <span className="absolute left-[21px] top-0 bottom-0 w-px bg-zinc-800/80" />
        <span className="text-[11px] text-zinc-500 tabular-nums font-mono">
          {formatTime(span.started_at)}
        </span>
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <StatusDot status={span.status} />
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <div className="flex flex-col min-w-0">
          <span className="text-[12px] text-zinc-200 truncate max-w-[260px]">
            {span.model}
          </span>
          <span className="text-[10px] text-zinc-500 capitalize">
            {span.provider}
          </span>
        </div>
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <LatencyText ms={span.latency_ms} muted />
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <span className="text-xs font-mono text-zinc-400 tabular-nums">
          {span.cost_usd ? `$${parseFloat(span.cost_usd).toFixed(6)}` : "—"}
        </span>
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <div className="text-xs tabular-nums">
          <div className="text-zinc-300 font-mono">
            {span.total_tokens !== null
              ? span.total_tokens.toLocaleString()
              : "—"}
          </div>
          {span.input_tokens !== null && span.output_tokens !== null && (
            <div className="text-[10px] text-zinc-500 font-mono">
              {span.input_tokens.toLocaleString()} ·{" "}
              {span.output_tokens.toLocaleString()}
            </div>
          )}
        </div>
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <HallucinationText score={span.hallucination_score} muted />
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <span className="text-[11px] text-zinc-600">{span.environment}</span>
      </td>

      <td className="px-4 py-2 whitespace-nowrap">
        <span className="font-mono text-[10px] text-zinc-600">
          {span.id.slice(0, 8)}
        </span>
      </td>
    </tr>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

function TracesInner() {
  const { data: session } = useSession();
  const router = useRouter();
  const { filters, setFilter, clearFilters, activeCount } = useTracesFilters();
  const { projectId: activeProjectId } = useProject();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const token = session?.accessToken as string | undefined;
  const projectId = activeProjectId || "";

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useInfiniteQuery({
      queryKey: ["spans", projectId, filters],
      queryFn: ({ pageParam }) =>
        spans.list(
          projectId,
          { ...filters, cursor: pageParam as string | undefined },
          token!,
        ),
      getNextPageParam: (lastPage) =>
        lastPage.has_more ? lastPage.next_cursor : undefined,
      initialPageParam: undefined as string | undefined,
      enabled: !!token && !!projectId,
    });

  const allItems = data?.pages.flatMap((p) => p.items) ?? [];
  const totalHint = data?.pages[0]?.total_hint ?? 0;

  const groups = useMemo(() => groupByEndpoint(allItems), [allItems]);

  const toggle = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const openSpan = useCallback(
    (id: string) => router.push(`/dashboard/traces/${id}`),
    [router],
  );

  const expandAll = () => {
    const multi = groups.filter((g) => g.spans.length > 1).map((g) => g.key);
    setExpanded(new Set(multi));
  };
  const collapseAll = () => setExpanded(new Set());

  const multiGroupCount = groups.filter((g) => g.spans.length > 1).length;

  return (
    <div className="flex flex-col min-h-screen bg-zinc-950">
      <Topbar title="Traces" />

      <div className="flex-1 px-6 lg:px-10 py-6">
        <div className="max-w-6xl mx-auto space-y-5">
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-xl font-medium text-zinc-50 tracking-tight">
                Traces
              </h1>
              <p className="text-[12px] text-zinc-500 mt-0.5">
                {isLoading ? (
                  "Loading…"
                ) : (
                  <>
                    {groups.length.toLocaleString()} endpoint
                    {groups.length === 1 ? "" : "s"} ·{" "}
                    {totalHint.toLocaleString()} call
                    {totalHint === 1 ? "" : "s"}
                  </>
                )}
                {activeCount > 0 && (
                  <span className="ml-1.5 text-lime-400">(filtered)</span>
                )}
              </p>
            </div>
            <FilterBar
              filters={filters}
              setFilter={setFilter}
              clearFilters={clearFilters}
              activeCount={activeCount}
            />
          </div>

          {!isLoading && allItems.length > 0 && (
            <SummaryStrip items={allItems} endpointCount={groups.length} />
          )}

          <div className="border border-zinc-800/70 rounded-lg overflow-hidden">
            {/* Table toolbar: expand/collapse all (only if any multi-call groups) */}
            {!isLoading && multiGroupCount > 0 && (
              <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/70 bg-zinc-900/40">
                <span className={LABEL}>
                  Grouped by endpoint — {multiGroupCount.toLocaleString()}{" "}
                  endpoint{multiGroupCount === 1 ? "" : "s"} with multiple calls
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={expandAll}
                    className="text-[11px] text-zinc-400 hover:text-zinc-100 px-2 h-6 rounded transition-colors"
                  >
                    Expand all
                  </button>
                  <span className="text-zinc-700">·</span>
                  <button
                    onClick={collapseAll}
                    className="text-[11px] text-zinc-400 hover:text-zinc-100 px-2 h-6 rounded transition-colors"
                  >
                    Collapse all
                  </button>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800/70 bg-zinc-900/40">
                    {HEADERS.map((h) => (
                      <th
                        key={h}
                        className="text-left px-4 py-2.5 text-[10px] font-medium text-zinc-500 uppercase tracking-[0.14em] whitespace-nowrap"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td
                        colSpan={HEADERS.length}
                        className="px-4 py-16 text-center text-zinc-500 text-xs"
                      >
                        Loading spans…
                      </td>
                    </tr>
                  ) : groups.length === 0 ? (
                    <tr>
                      <td
                        colSpan={HEADERS.length}
                        className="px-4 py-16 text-center text-zinc-500 text-xs"
                      >
                        No spans found
                      </td>
                    </tr>
                  ) : (
                    groups.map((group) => {
                      const isMulti = group.spans.length > 1;
                      const isOpen = expanded.has(group.key);
                      return (
                        <Fragment key={group.key}>
                          <GroupRow
                            group={group}
                            expanded={isOpen}
                            onToggle={() => toggle(group.key)}
                            onOpenSpan={openSpan}
                          />
                          {isMulti &&
                            isOpen &&
                            group.spans.map((s) => (
                              <ChildRow
                                key={s.id}
                                span={s}
                                onOpen={openSpan}
                              />
                            ))}
                        </Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {hasNextPage && (
              <div className="px-4 py-2.5 border-t border-zinc-800/70 text-center bg-zinc-900/30">
                <button
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="text-[12px] text-zinc-400 hover:text-zinc-100 disabled:text-zinc-700 transition-colors"
                >
                  {isFetchingNextPage ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function TracesPage() {
  return (
    <Suspense
      fallback={<div className="p-6 text-xs text-zinc-500">Loading…</div>}
    >
      <TracesInner />
    </Suspense>
  );
}
