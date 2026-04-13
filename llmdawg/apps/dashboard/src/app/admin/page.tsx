"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Copy, Check, X, Activity, DollarSign, Clock, ShieldAlert } from "lucide-react";
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        {!created ? (
          <>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-gray-900">Add New Client</h2>
              <button onClick={onClose} className="p-1 rounded hover:bg-gray-100">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Client / Organization name
                </label>
                <input
                  type="text"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="e.g. Acme Corp"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Project name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Production API"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  onKeyDown={(e) => e.key === "Enter" && mutation.mutate()}
                />
              </div>
            </div>

            {error && (
              <p className="mt-3 text-sm text-red-600">{error}</p>
            )}

            <div className="flex gap-3 mt-6">
              <button
                onClick={onClose}
                className="flex-1 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => mutation.mutate()}
                disabled={!orgName.trim() || !projectName.trim() || mutation.isPending}
                className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {mutation.isPending ? "Creating…" : "Create"}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-1">
              <Check className="w-4 h-4 text-emerald-500" />
              <h2 className="text-base font-semibold text-gray-900">Client created</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              <span className="font-medium text-gray-800">{created.org_name}</span>
              {" / "}
              <span className="font-medium text-gray-800">{created.project_name}</span>
            </p>

            <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
              Share this key with the client. It will never be shown again.
            </p>

            <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 mb-6">
              <code className="flex-1 font-mono text-xs text-gray-800 break-all">
                {created.api_key}
              </code>
              <button
                onClick={copy}
                className="flex-shrink-0 p-1 rounded hover:bg-gray-200"
                title="Copy key"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-emerald-500" />
                ) : (
                  <Copy className="w-4 h-4 text-gray-500" />
                )}
              </button>
            </div>

            <button
              onClick={onClose}
              className="w-full py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
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
  color,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-500">{label}</span>
        <div className={cn("p-2 rounded-lg", color)}>
          <Icon className="w-4 h-4 text-white" />
        </div>
      </div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { data: session } = useSession();
  const [showModal, setShowModal] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const token = (session as any)?.accessToken as string | undefined;

  const { data: rows = [], isLoading, error } = useQuery({
    queryKey: ["admin-projects"],
    queryFn: () => admin.listProjects(token!),
    enabled: !!token,
    retry: false,
  });

  const totalSpans = rows.reduce((sum, r) => sum + r.span_count, 0);
  const totalCost = rows.reduce((sum, r) => sum + r.total_cost_usd, 0);
  const activeClients = new Set(rows.map((r) => r.org_id)).size;

  const formatCost = (v: number) =>
    v < 0.001 ? `$${v.toFixed(6)}` : `$${v.toFixed(2)}`;

  const formatDate = (s: string | null) =>
    s ? new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";

  const isUnauthorized = error instanceof ApiError && error.status === 403;

  if (isUnauthorized) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <ShieldAlert className="w-10 h-10 text-red-400 mx-auto mb-3" />
          <h1 className="text-lg font-semibold text-gray-900">Access Denied</h1>
          <p className="text-sm text-gray-500 mt-1">
            Your email is not in the admin list. Add it to <code className="text-xs bg-gray-100 px-1 rounded">ADMIN_EMAILS</code> in your <code className="text-xs bg-gray-100 px-1 rounded">.env</code>.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-900">WhyLLM Admin</h1>
            <p className="text-sm text-gray-500">All clients and projects</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Client
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <StatCard
            label="Total Clients"
            value={isLoading ? "…" : activeClients.toLocaleString()}
            icon={Activity}
            color="bg-indigo-500"
          />
          <StatCard
            label="Total Spans"
            value={isLoading ? "…" : totalSpans.toLocaleString()}
            icon={Clock}
            color="bg-violet-500"
          />
          <StatCard
            label="Total Cost"
            value={isLoading ? "…" : formatCost(totalCost)}
            icon={DollarSign}
            color="bg-emerald-500"
          />
        </div>

        {/* Projects table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-900">
              All Projects{" "}
              {!isLoading && (
                <span className="ml-1 text-gray-400 font-normal">({rows.length})</span>
              )}
            </h2>
          </div>

          {isLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-sm text-gray-400">No projects yet. Add your first client.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Client
                  </th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Project
                  </th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Spans
                  </th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Last Active
                  </th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.map((row: AdminProjectRow) => (
                  <tr key={row.project_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3.5">
                      <span className="font-medium text-gray-900">{row.org_name}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-700">{row.project_name}</span>
                        <span className="font-mono text-xs text-gray-400">{row.project_slug}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-right tabular-nums text-gray-600">
                      {row.span_count.toLocaleString()}
                    </td>
                    <td className="px-5 py-3.5 text-right tabular-nums text-gray-600">
                      {formatCost(row.total_cost_usd)}
                    </td>
                    <td className="px-5 py-3.5 text-right text-gray-500">
                      {formatDate(row.last_active_at)}
                    </td>
                    <td className="px-5 py-3.5 text-right text-gray-500">
                      {formatDate(row.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showModal && token && (
        <AddClientModal token={token} onClose={() => setShowModal(false)} />
      )}
    </div>
  );
}
