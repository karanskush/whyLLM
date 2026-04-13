"use client";

import { useCallback, useState, Suspense } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Search, X, ChevronDown } from "lucide-react";
import { spans, type SpanListItem, type SpanFilters } from "@/lib/api";
import { Topbar } from "@/components/layout/topbar";
import { useProject } from "@/hooks/useProject";
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
    <span className={cn("px-2 py-0.5 rounded-full text-xs font-medium", color)}>
      {status}
    </span>
  );
}

// ── URL-persistent filters ─────────────────────────────────────────────────────

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
      if (value === undefined || value === "") {
        params.delete(key);
      } else {
        params.set(key, String(value));
      }
      router.push(`${pathname}?${params.toString()}`);
    },
    [router, pathname, searchParams],
  );

  const clearFilters = useCallback(() => {
    router.push(pathname);
  }, [router, pathname]);

  const activeCount = Object.values(filters).filter(
    (v) => v !== undefined && v !== 50,
  ).length;

  return { filters, setFilter, clearFilters, activeCount };
}

// ── Column helper ─────────────────────────────────────────────────────────────

const col = createColumnHelper<SpanListItem>();

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const columns: any[] = [
  col.accessor("started_at", {
    header: "Time",
    cell: (info) => {
      const v = info.getValue() as string | null;
      if (!v) return "—";
      return new Date(v).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    },
  }),
  col.accessor("status", {
    header: "Status",
    cell: (info) => <StatusBadge status={info.getValue() as string} />,
  }),
  col.accessor("model", {
    header: "Model",
    cell: (info) => (
      <span className="font-mono text-xs text-gray-700">{info.getValue() as string}</span>
    ),
  }),
  col.accessor("provider", {
    header: "Provider",
    cell: (info) => (
      <span className="capitalize text-xs text-gray-500">{info.getValue() as string}</span>
    ),
  }),
  col.accessor("latency_ms", {
    header: "Latency",
    cell: (info) => {
      const v = info.getValue() as number | null;
      return v !== null ? `${v.toLocaleString()} ms` : "—";
    },
  }),
  col.accessor("cost_usd", {
    header: "Cost",
    cell: (info) => {
      const v = info.getValue() as string | null;
      return v ? `$${parseFloat(v).toFixed(6)}` : "—";
    },
  }),
  col.accessor("total_tokens", {
    header: "Tokens",
    cell: (info) => {
      const v = info.getValue() as number | null;
      return v !== null ? v.toLocaleString() : "—";
    },
  }),
  col.accessor("hallucination_score", {
    header: "Hall.",
    cell: (info) => {
      const v = info.getValue() as string | null;
      if (!v) return "—";
      const score = parseFloat(v);
      const color =
        score > 0.3 ? "text-red-600 font-semibold" : "text-gray-500";
      return <span className={color}>{score.toFixed(2)}</span>;
    },
  }),
  col.accessor("environment", {
    header: "Env",
    cell: (info) => (
      <span className="text-xs text-gray-400">{info.getValue() as string}</span>
    ),
  }),
  col.accessor("trace_id", {
    header: "Trace",
    cell: (info) => {
      const v = info.getValue() as string | null;
      return v ? (
        <span className="font-mono text-xs text-indigo-500">
          {v.slice(0, 8)}…
        </span>
      ) : (
        "—"
      );
    },
  }),
];

// ── Filter bar ────────────────────────────────────────────────────────────────

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
    <div className="flex flex-wrap items-center gap-2 pb-3">
      <FilterSelect
        label="Status"
        value={filters.status || ""}
        options={["", "success", "error", "streaming", "cancelled"]}
        onChange={(v) => setFilter("status", v || undefined)}
      />
      <FilterSelect
        label="Provider"
        value={filters.provider || ""}
        options={["", "openai", "anthropic", "google", "cohere"]}
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
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-800 px-2 py-1.5 rounded border border-gray-200 hover:border-gray-300"
        >
          <X className="w-3 h-3" />
          Clear ({activeCount})
        </button>
      )}
    </div>
  );
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
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "appearance-none pl-2 pr-6 py-1.5 text-xs rounded border bg-white cursor-pointer",
          value
            ? "border-indigo-400 text-indigo-700 bg-indigo-50"
            : "border-gray-200 text-gray-600",
        )}
      >
        <option value="">{label}</option>
        {options.slice(1).map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-1 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
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
      <Search className="absolute left-2 w-3 h-3 text-gray-400" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Model…"
        className="pl-6 pr-2 py-1.5 text-xs rounded border border-gray-200 bg-white w-36 focus:outline-none focus:border-indigo-400"
      />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

function TracesInner() {
  const { data: session } = useSession();
  const router = useRouter();
  const { filters, setFilter, clearFilters, activeCount } = useTracesFilters();
  const { projectId: activeProjectId } = useProject();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  const projectId = activeProjectId || "";

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useInfiniteQuery({
      queryKey: ["spans", projectId, filters],
      queryFn: ({ pageParam }) =>
        spans.list(projectId, { ...filters, cursor: pageParam as string | undefined }, token!),
      getNextPageParam: (lastPage) =>
        lastPage.has_more ? lastPage.next_cursor : undefined,
      initialPageParam: undefined as string | undefined,
      enabled: !!token && !!projectId,
    });

  const allItems = data?.pages.flatMap((p) => p.items) ?? [];
  const totalHint = data?.pages[0]?.total_hint ?? 0;

  const table = useReactTable({
    data: allItems,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      <Topbar title="Traces Explorer" />

      <div className="flex-1 p-6">
        {/* Summary bar */}
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm text-gray-500">
            {isLoading ? "Loading…" : `${totalHint.toLocaleString()} spans`}
            {activeCount > 0 && (
              <span className="ml-1 text-indigo-600">(filtered)</span>
            )}
          </p>
        </div>

        {/* Filters */}
        <FilterBar
          filters={filters}
          setFilter={setFilter}
          clearFilters={clearFilters}
          activeCount={activeCount}
        />

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id} className="border-b border-gray-100 bg-gray-50">
                    {hg.headers.map((header) => (
                      <th
                        key={header.id}
                        className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap"
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="px-4 py-12 text-center text-gray-400 text-sm"
                    >
                      Loading spans…
                    </td>
                  </tr>
                ) : allItems.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="px-4 py-12 text-center text-gray-400 text-sm"
                    >
                      No spans found
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() =>
                        router.push(
                          `/dashboard/traces/${row.original.id}`,
                        )
                      }
                      className="border-b border-gray-50 hover:bg-indigo-50 cursor-pointer transition-colors"
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td
                          key={cell.id}
                          className="px-4 py-3 whitespace-nowrap"
                        >
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext(),
                          )}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Load more */}
          {hasNextPage && (
            <div className="px-4 py-3 border-t border-gray-100 text-center">
              <button
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="text-sm text-indigo-600 hover:text-indigo-800 disabled:text-gray-400"
              >
                {isFetchingNextPage ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TracesPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-gray-400">Loading…</div>}>
      <TracesInner />
    </Suspense>
  );
}
