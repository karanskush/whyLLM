"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { redirect } from "next/navigation";
import { Plus, Copy, Check, X, Activity, DollarSign, Clock } from "lucide-react";
import { admin, type AdminProjectRow, type CreateClientResponse, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Add Client Modal ──────────────────────────────────────────────────────────

function AddClientModal({
  token,
  onClose,
}: {
  token: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [orgName, setOrgName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [created, setCreated] = useState<CreateClientResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      admin.createClient({ org_name: orgName.trim(), project_name: projectName.trim() }, token),
    onSuccess: (data) => {
      setCreated(data);
      queryClient.invalidateQueries({ queryKey: ["admin-projects"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 403) {
        setError("You don't have admin access.");
      } else {
        setError("Failed to create client. Try again.");
      }
    },
  });

  const copy = () => {
    if (!created) return;
    navigator.clipboard.writeText(created.api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-full max-w-md p-6">
        {!created ? (
          <>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-white">Onboard New Client</h2>
              <button onClick={onClose} className="p-1 rounded hover:bg-zinc-800 transition-colors">
                <X className="w-4 h-4 text-zinc-500" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                  Client / Organization name
                </label>
                <input
                  type="text"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="e.g. Acme Corp"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                  Project name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Production API"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
                  onKeyDown={(e) => e.key === "Enter" && mutation.mutate()}
                />
              </div>
            </div>

            {error && (
              <div className="mt-3 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-400">
                {error}
              </div>
            )}

            <div className="flex gap-3 mt-6">
              <button
                onClick={onClose}
                className="flex-1 py-2 rounded-lg border border-zinc-700 text-sm font-medium text-zinc-400 hover:bg-zinc-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => mutation.mutate()}
                disabled={!orgName.trim() || !projectName.trim() || mutation.isPending}
                className="flex-1 py-2 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 disabled:opacity-50 transition-colors"
              >
                {mutation.isPending ? "Creating…" : "Onboard Client"}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-1">
              <Check className="w-4 h-4 text-emerald-400" />
              <h2 className="text-base font-semibold text-white">Client onboarded</h2>
            </div>
            <p className="text-sm text-zinc-400 mb-4">
              <span className="font-medium text-zinc-200">{created.org_name}</span>
              {" / "}
              <span className="font-medium text-zinc-200">{created.project_name}</span>
            </p>

            <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mb-4">
              Share this key with the client. It will never be shown again.
            </p>

            <div className="flex items-center gap-2 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 mb-6">
              <code className="flex-1 font-mono text-xs text-zinc-300 break-all">
                {created.api_key}
              </code>
              <button
                onClick={copy}
                className="flex-shrink-0 p-1 rounded hover:bg-zinc-700 transition-colors"
                title="Copy key"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-emerald-400" />
                ) : (
                  <Copy className="w-4 h-4 text-zinc-500" />
                )}
              </button>
            </div>

            <button
              onClick={onClose}
              className="w-full py-2 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 transition-colors"
            >
              Done
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── Stats card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
  iconBg,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  iconBg: string;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-zinc-500">{label}</span>
        <div className={cn("p-2 rounded-lg", iconBg)}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { data: session, status } = useSession();
  const [showModal, setShowModal] = useState(false);

  const token = session?.accessToken as string | undefined;
  const isAdmin = session?.isAdmin;

  if (status !== "loading" && !isAdmin) {
    redirect("/dashboard");
  }

  const { data: rows = [], isLoading, error } = useQuery({
    queryKey: ["admin-projects"],
    queryFn: () => admin.listProjects(token!),
    enabled: !!token && !!isAdmin,
    retry: false,
  });

  const totalSpans = rows.reduce((sum, r) => sum + r.span_count, 0);
  const totalCost = rows.reduce((sum, r) => sum + r.total_cost_usd, 0);
  const activeClients = new Set(rows.map((r) => r.org_id)).size;

  const formatCost = (v: number) =>
    v < 0.001 ? `$${v.toFixed(6)}` : `$${v.toFixed(2)}`;

  const formatDate = (s: string | null) =>
    s
      ? new Date(s).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })
      : "—";

  if (status === "loading") {
    return (
      <div className="p-6 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 bg-zinc-800 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white">Clients</h1>
          <p className="text-sm text-zinc-500">All organizations and their projects</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-lime-500 text-black text-sm font-semibold rounded-lg hover:bg-lime-400 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Onboard Client
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          label="Total Clients"
          value={isLoading ? "…" : activeClients.toLocaleString()}
          icon={Activity}
          iconBg="bg-lime-500/10 text-lime-400"
        />
        <StatCard
          label="Total Spans"
          value={isLoading ? "…" : totalSpans.toLocaleString()}
          icon={Clock}
          iconBg="bg-violet-500/10 text-violet-400"
        />
        <StatCard
          label="Total Cost"
          value={isLoading ? "…" : formatCost(totalCost)}
          icon={DollarSign}
          iconBg="bg-emerald-500/10 text-emerald-400"
        />
      </div>

      {/* Projects table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-white">
            All Projects{" "}
            {!isLoading && (
              <span className="ml-1 text-zinc-500 font-normal">({rows.length})</span>
            )}
          </h2>
        </div>

        {isLoading ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-zinc-800 rounded animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="py-16 text-center">
            <p className="text-sm text-red-400">Failed to load projects.</p>
          </div>
        ) : rows.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-zinc-500">No clients yet. Onboard your first client.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-800/50">
                <th className="text-left px-5 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Client
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Project
                </th>
                <th className="text-right px-5 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Spans
                </th>
                <th className="text-right px-5 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Cost
                </th>
                <th className="text-right px-5 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Last Active
                </th>
                <th className="text-right px-5 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {rows.map((row: AdminProjectRow) => (
                <tr key={row.project_id} className="hover:bg-zinc-800/40 transition-colors">
                  <td className="px-5 py-3.5">
                    <span className="font-medium text-white">{row.org_name}</span>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-300">{row.project_name}</span>
                      <span className="font-mono text-xs text-zinc-600">{row.project_slug}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-right tabular-nums text-zinc-400">
                    {row.span_count.toLocaleString()}
                  </td>
                  <td className="px-5 py-3.5 text-right tabular-nums text-zinc-400">
                    {formatCost(row.total_cost_usd)}
                  </td>
                  <td className="px-5 py-3.5 text-right text-zinc-500">
                    {formatDate(row.last_active_at)}
                  </td>
                  <td className="px-5 py-3.5 text-right text-zinc-500">
                    {formatDate(row.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && token && (
        <AddClientModal token={token} onClose={() => setShowModal(false)} />
      )}
    </div>
  );
}
