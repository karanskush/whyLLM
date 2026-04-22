"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Bell, Play, ToggleLeft, ToggleRight } from "lucide-react";
import { settings, type AlertResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const METRICS = [
  "cost_usd",
  "error_rate",
  "latency_p95",
  "latency_p50",
  "hallucination_score",
  "span_count",
] as const;

const CONDITIONS = ["gt", "lt", "gte", "lte"] as const;
const CONDITION_LABELS: Record<string, string> = {
  gt: ">",
  lt: "<",
  gte: "≥",
  lte: "≤",
};

interface Props {
  projectId: string;
  token: string;
}

export function AlertsTab({ projectId, token }: Props) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [metric, setMetric] = useState<string>("cost_usd");
  const [condition, setCondition] = useState<string>("gt");
  const [threshold, setThreshold] = useState("");
  const [windowMinutes, setWindowMinutes] = useState("60");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ["alerts", projectId],
    queryFn: () => settings.listAlerts(projectId, token),
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      settings.createAlert(
        projectId,
        {
          name,
          metric,
          condition,
          threshold,
          window_minutes: parseInt(windowMinutes) || 60,
          channels: webhookUrl
            ? [{ type: "webhook", target: webhookUrl }]
            : undefined,
        },
        token,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts", projectId] });
      setShowForm(false);
      setName("");
      setThreshold("");
      setWebhookUrl("");
      setFormError(null);
    },
    onError: () => setFormError("Failed to create alert. Check values and try again."),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      settings.toggleAlert(projectId, id, is_active, token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts", projectId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => settings.deleteAlert(projectId, id, token),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts", projectId] }),
  });

  const testMutation = useMutation({
    mutationFn: (id: string) => settings.testAlert(projectId, id, token),
  });

  const metricLabel = (m: string) =>
    m
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());

  const inputCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors";

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-zinc-500">
          Get notified when metrics cross thresholds.
        </p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 bg-lime-500 text-black text-sm font-semibold rounded-lg hover:bg-lime-400 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Alert
        </button>
      </div>

      {showForm && (
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-4 mb-4 space-y-3">
          <h4 className="text-sm font-medium text-zinc-200">New alert</h4>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-zinc-500 mb-1.5">Alert name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. High cost spike"
                className={inputCls}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1.5">Metric</label>
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
                className={inputCls}
              >
                {METRICS.map((m) => (
                  <option key={m} value={m}>
                    {metricLabel(m)}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1.5">Condition</label>
                <select
                  value={condition}
                  onChange={(e) => setCondition(e.target.value)}
                  className={inputCls}
                >
                  {CONDITIONS.map((c) => (
                    <option key={c} value={c}>
                      {CONDITION_LABELS[c]} ({c})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1.5">Threshold</label>
                <input
                  type="number"
                  step="any"
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  placeholder="10.00"
                  className={inputCls}
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1.5">Window (minutes)</label>
              <input
                type="number"
                min="1"
                value={windowMinutes}
                onChange={(e) => setWindowMinutes(e.target.value)}
                className={inputCls}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                Webhook URL (optional)
              </label>
              <input
                type="url"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                placeholder="https://hooks.slack.com/…"
                className={inputCls}
              />
            </div>
          </div>
          {formError && <p className="text-xs text-red-400">{formError}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => { setShowForm(false); setFormError(null); }}
              className="px-3 py-1.5 rounded-lg border border-zinc-700 text-sm text-zinc-400 hover:bg-zinc-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={!name || !threshold || createMutation.isPending}
              className="px-3 py-1.5 rounded-lg bg-lime-500 text-black text-sm font-semibold hover:bg-lime-400 disabled:opacity-40 transition-colors"
            >
              {createMutation.isPending ? "Saving…" : "Save alert"}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 bg-zinc-800 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="py-12 text-center">
          <Bell className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
          <p className="text-sm text-zinc-500">No alerts configured. Add one to get notified.</p>
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 border border-zinc-800 rounded-xl overflow-hidden">
          {alerts.map((alert: AlertResponse) => (
            <div
              key={alert.id}
              className={cn(
                "flex items-center gap-4 px-4 py-3.5 bg-zinc-900 hover:bg-zinc-800/50 transition-colors",
                !alert.is_active && "opacity-50",
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-200">{alert.name}</span>
                </div>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-zinc-500">
                  <span className="font-mono">
                    {metricLabel(alert.metric)} {CONDITION_LABELS[alert.condition] ?? alert.condition}{" "}
                    {alert.threshold}
                  </span>
                  <span className="text-zinc-700">·</span>
                  <span>{alert.window_minutes}m window</span>
                  {alert.channels.length > 0 && (
                    <>
                      <span className="text-zinc-700">·</span>
                      <span>{alert.channels.length} channel{alert.channels.length !== 1 ? "s" : ""}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={() => testMutation.mutate(alert.id)}
                  disabled={testMutation.isPending}
                  className="p-1.5 rounded-lg text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                  title="Test alert"
                >
                  <Play className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() =>
                    toggleMutation.mutate({ id: alert.id, is_active: !alert.is_active })
                  }
                  disabled={toggleMutation.isPending}
                  className="p-1.5 rounded-lg text-zinc-600 hover:bg-zinc-800 transition-colors"
                  title={alert.is_active ? "Disable" : "Enable"}
                >
                  {alert.is_active ? (
                    <ToggleRight className="w-4 h-4 text-lime-400" />
                  ) : (
                    <ToggleLeft className="w-4 h-4 text-zinc-600" />
                  )}
                </button>
                <button
                  onClick={() => deleteMutation.mutate(alert.id)}
                  disabled={deleteMutation.isPending}
                  className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  title="Delete alert"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
