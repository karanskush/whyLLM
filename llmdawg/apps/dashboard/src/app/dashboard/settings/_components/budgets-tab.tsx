"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, ShieldAlert } from "lucide-react";
import { settings, type BudgetResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const PERIODS = ["daily", "weekly", "monthly"] as const;
const ACTIONS = ["alert", "block"] as const;

interface Props {
  projectId: string;
  token: string;
}

export function BudgetsTab({ projectId, token }: Props) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [amount, setAmount] = useState("");
  const [period, setPeriod] = useState<"daily" | "weekly" | "monthly">("daily");
  const [action, setAction] = useState<"alert" | "block">("alert");
  const [formError, setFormError] = useState<string | null>(null);

  const { data: budgets = [], isLoading } = useQuery({
    queryKey: ["budgets", projectId],
    queryFn: () => settings.listBudgets(projectId, token),
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      settings.createBudget(projectId, { amount_usd: amount, period, action }, token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["budgets", projectId] });
      setShowForm(false);
      setAmount("");
      setFormError(null);
    },
    onError: () => setFormError("Failed to create budget. Check amount and try again."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => settings.deleteBudget(projectId, id, token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["budgets", projectId] }),
  });

  const periodBadge = (p: string) => {
    const map: Record<string, string> = {
      daily: "bg-blue-100 text-blue-700",
      weekly: "bg-violet-100 text-violet-700",
      monthly: "bg-indigo-100 text-indigo-700",
    };
    return map[p] ?? "bg-gray-100 text-gray-700";
  };

  const actionBadge = (a: string) => {
    return a === "block"
      ? "bg-red-100 text-red-700"
      : "bg-amber-100 text-amber-700";
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">
          Set spend limits. Budgets can alert or block requests when exceeded.
        </p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700"
        >
          <Plus className="w-4 h-4" />
          Add Budget
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
          <h4 className="text-sm font-medium text-gray-800 mb-3">New budget</h4>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Amount (USD)
              </label>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="10.00"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Period</label>
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value as typeof period)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                When exceeded
              </label>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value as typeof action)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>
                    {a.charAt(0).toUpperCase() + a.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {formError && <p className="mt-2 text-xs text-red-600">{formError}</p>}
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => { setShowForm(false); setFormError(null); }}
              className="px-3 py-1.5 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={!amount || createMutation.isPending}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {createMutation.isPending ? "Saving…" : "Save budget"}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-14 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : budgets.length === 0 ? (
        <div className="py-12 text-center text-sm text-gray-400">
          <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-gray-300" />
          No budgets configured. Add one to control spend.
        </div>
      ) : (
        <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
          {budgets.map((b: BudgetResponse) => (
            <div
              key={b.id}
              className="flex items-center gap-4 px-4 py-3 bg-white hover:bg-gray-50"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">
                    ${parseFloat(b.amount_usd).toFixed(2)}
                  </span>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", periodBadge(b.period))}>
                    {b.period}
                  </span>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", actionBadge(b.action))}>
                    {b.action}
                  </span>
                  {!b.is_active && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                      inactive
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-xs text-gray-400">
                  Created {new Date(b.created_at).toLocaleDateString()}
                </div>
              </div>
              <button
                onClick={() => deleteMutation.mutate(b.id)}
                disabled={deleteMutation.isPending}
                className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
