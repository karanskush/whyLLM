"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, ShieldAlert } from "lucide-react";
import { settings, type BudgetResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const PERIODS = ["daily", "weekly", "monthly"] as const;
const ACTIONS = ["alert", "block"] as const;

export function BudgetsTab({ projectId, token }: { projectId: string; token: string }) {
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
    mutationFn: () => settings.createBudget(projectId, { amount_usd: amount, period, action }, token),
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

  const periodBadge = (p: string) => ({
    daily: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
    weekly: "bg-violet-500/10 text-violet-400 border border-violet-500/20",
    monthly: "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20",
  }[p] ?? "bg-zinc-800 text-zinc-400 border border-zinc-700");

  const actionBadge = (a: string) =>
    a === "block"
      ? "bg-red-500/10 text-red-400 border border-red-500/20"
      : "bg-amber-500/10 text-amber-400 border border-amber-500/20";

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-zinc-500">Set spend limits. Budgets can alert or block requests when exceeded.</p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 bg-lime-500 text-black text-sm font-semibold rounded-lg hover:bg-lime-400 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Budget
        </button>
      </div>

      {showForm && (
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-4 mb-4">
          <h4 className="text-sm font-medium text-zinc-200 mb-3">New budget</h4>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1.5">Amount (USD)</label>
              <input
                type="number" min="0.01" step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="10.00"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1.5">Period</label>
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value as typeof period)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-600"
              >
                {PERIODS.map((p) => <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1.5">When exceeded</label>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value as typeof action)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-600"
              >
                {ACTIONS.map((a) => <option key={a} value={a}>{a.charAt(0).toUpperCase() + a.slice(1)}</option>)}
              </select>
            </div>
          </div>
          {formError && <p className="mt-2 text-xs text-red-400">{formError}</p>}
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => { setShowForm(false); setFormError(null); }}
              className="px-3 py-1.5 rounded-lg border border-zinc-700 text-sm text-zinc-400 hover:bg-zinc-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={!amount || createMutation.isPending}
              className="px-3 py-1.5 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 disabled:opacity-40 transition-colors"
            >
              {createMutation.isPending ? "Saving…" : "Save budget"}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <div key={i} className="h-14 bg-zinc-800 rounded-lg animate-pulse" />)}
        </div>
      ) : budgets.length === 0 ? (
        <div className="py-12 text-center">
          <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
          <p className="text-sm text-zinc-500">No budgets configured. Add one to control spend.</p>
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 border border-zinc-800 rounded-xl overflow-hidden">
          {budgets.map((b: BudgetResponse) => (
            <div key={b.id} className="flex items-center gap-4 px-4 py-3.5 bg-zinc-900 hover:bg-zinc-800/50 transition-colors">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-zinc-200">${parseFloat(b.amount_usd).toFixed(2)}</span>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", periodBadge(b.period))}>{b.period}</span>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", actionBadge(b.action))}>{b.action}</span>
                  {!b.is_active && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500 border border-zinc-700">inactive</span>
                  )}
                </div>
                <div className="mt-0.5 text-xs text-zinc-600">Created {new Date(b.created_at).toLocaleDateString()}</div>
              </div>
              <button
                onClick={() => deleteMutation.mutate(b.id)}
                disabled={deleteMutation.isPending}
                className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
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
