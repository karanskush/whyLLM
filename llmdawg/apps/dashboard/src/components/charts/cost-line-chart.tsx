"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { format, parseISO } from "date-fns";
import type { TimeseriesPoint } from "@/lib/api";

interface CostLineChartProps {
  series: TimeseriesPoint[];
  granularity: "hour" | "day" | string;
}

const COLORS = [
  "#6366f1", "#f59e0b", "#10b981", "#ef4444",
  "#3b82f6", "#8b5cf6", "#06b6d4", "#f97316",
];

export function CostLineChart({ series, granularity }: CostLineChartProps) {
  if (!series.length) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-gray-400">
        No data in this time window
      </div>
    );
  }

  // Aggregate by bucket, one entry per (bucket, model)
  const models = Array.from(new Set(series.map((s) => s.model)));
  const byBucket = new Map<string, Record<string, number>>();

  for (const point of series) {
    if (!byBucket.has(point.bucket)) byBucket.set(point.bucket, {});
    byBucket.get(point.bucket)![point.model] = point.cost_usd;
  }

  const chartData = Array.from(byBucket.entries()).map(([bucket, costs]) => ({
    bucket,
    label: format(parseISO(bucket), granularity === "hour" ? "HH:mm" : "MMM d"),
    ...costs,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v.toFixed(4)}`}
        />
        <Tooltip
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={(value: any, name: any) => [`$${Number(value).toFixed(6)}`, name as string]}
          labelStyle={{ fontSize: 12 }}
          contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e7eb" }}
        />
        {models.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {models.map((model, i) => (
          <Line
            key={model}
            type="monotone"
            dataKey={model}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
