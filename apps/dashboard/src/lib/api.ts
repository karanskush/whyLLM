/**
 * Typed API client for the whyllm backend.
 *
 * All requests include the session access token from NextAuth.
 * Throws on non-2xx responses with a structured error.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`API error ${status}`);
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, ...init } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface UserResponse {
  id: string;
  email: string;
  name: string | null;
  org_id: string | null;
  org_name: string | null;
  is_admin: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserResponse;
}

export const auth = {
  register: (body: { email: string; password: string; name?: string; org_name?: string }) =>
    request<TokenResponse>("/api/v1/auth/register", { method: "POST", body: JSON.stringify(body) }),

  login: (body: { email: string; password: string }) =>
    request<TokenResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(body) }),

  me: (token: string) =>
    request<UserResponse>("/api/v1/auth/me", { token }),
};

// ── Metrics ───────────────────────────────────────────────────────────────────

export interface MetricsSummary {
  project_id: string;
  window: string;
  since: string;
  total_spans: number;
  total_cost_usd: number;
  error_count: number;
  error_rate: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  avg_hallucination_score: number | null;
}

export interface TimeseriesPoint {
  bucket: string;
  model: string;
  cost_usd: number;
  span_count: number;
}

export interface MetricsTimeseries {
  project_id: string;
  window: string;
  granularity: string;
  series: TimeseriesPoint[];
}

export type TimeWindow = "1h" | "6h" | "24h" | "7d" | "30d";

export const metrics = {
  summary: (projectId: string, window: TimeWindow, token: string) =>
    request<MetricsSummary>(`/v1/projects/${projectId}/metrics/summary?window=${window}`, { token }),

  timeseries: (projectId: string, window: TimeWindow, token: string) =>
    request<MetricsTimeseries>(`/v1/projects/${projectId}/metrics/timeseries?window=${window}`, { token }),
};

// ── Spans ─────────────────────────────────────────────────────────────────────

export interface SpanListItem {
  id: string;
  created_at: string;
  trace_id: string | null;
  project_id: string;
  provider: string;
  model: string;
  status: string;
  kind: string;
  name: string | null;
  environment: string;
  user_id: string | null;
  session_id: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cost_usd: string | null;
  latency_ms: number | null;
  ttft_ms: number | null;
  proxy_overhead_ms: number | null;
  hallucination_score: string | null;
  source: string;
  started_at: string | null;
}

export interface SpanTimings {
  // Provider self-reported server-side time (openai-processing-ms etc.)
  provider_processing_ms?: number;
  // Our observed TTFT (stream) or latency (non-stream) minus provider time
  network_rtt_ms?: number;
  provider_request_id?: string;
  provider_region?: string;
  provider?: string;
  rate_limit_remaining_tokens?: number;
  rate_limit_remaining_requests?: number;
  // Streaming-only rhythm data
  chunk_count?: number;
  first_chunk_ms?: number;
  last_chunk_ms?: number;
  inter_chunk_p50_ms?: number;
  inter_chunk_p95_ms?: number;
  inter_chunk_max_ms?: number;
  stall_count?: number;
  stall_total_ms?: number;
  stalls?: { at_ms: number; duration_ms: number }[];
  // [[arrival_ms, bytes], ...] — downsampled to ≤120 points
  timeline?: [number, number][];
}

export interface SpanDetailResponse extends SpanListItem {
  tags: Record<string, unknown>;
  request: Record<string, unknown> | null;
  response: Record<string, unknown> | null;
  hallucination_flags: Record<string, unknown> | null;
  error_type: string | null;
  error_message: string | null;
  ended_at: string | null;
  sdk_version: string | null;
  parent_span_id: string | null;
  timings: SpanTimings | null;
  siblings: SpanListItem[];
}

export interface SpanListResponse {
  items: SpanListItem[];
  next_cursor: string | null;
  has_more: boolean;
  total_hint: number;
}

export interface SpanFilters {
  model?: string;
  provider?: string;
  status?: string;
  environment?: string;
  user_id?: string;
  session_id?: string;
  trace_id?: string;
  started_after?: string;
  started_before?: string;
  min_cost?: string;
  max_cost?: string;
  has_hallucination?: boolean;
  limit?: number;
  cursor?: string;
}

export const spans = {
  list: (projectId: string, filters: SpanFilters, token: string) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined && v !== null && v !== "") {
        params.set(k, String(v));
      }
    }
    const qs = params.toString();
    return request<SpanListResponse>(
      `/v1/projects/${projectId}/spans${qs ? `?${qs}` : ""}`,
      { token },
    );
  },

  get: (spanId: string, token: string) =>
    request<SpanDetailResponse>(`/v1/spans/${spanId}`, { token }),

  feedback: (spanId: string, body: { feedback: string; note?: string }, token: string) =>
    request<void>(`/v1/spans/${spanId}/feedback`, {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
};

// ── Cost ──────────────────────────────────────────────────────────────────────

export interface CostBreakdownItem {
  model: string;
  provider: string;
  span_count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  pct_of_total: number;
}

export interface CostBreakdownResponse {
  project_id: string;
  window: string;
  since: string;
  total_cost_usd: number;
  items: CostBreakdownItem[];
  top_users: { user_id: string; cost_usd: number }[];
}

export const cost = {
  breakdown: (projectId: string, window: TimeWindow, token: string) =>
    request<CostBreakdownResponse>(
      `/v1/projects/${projectId}/cost/breakdown?window=${window}`,
      { token },
    ),
};

// ── Settings ──────────────────────────────────────────────────────────────────

export interface ApiKeyResponse {
  id: string;
  name: string;
  environment: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiKeyCreatedResponse extends ApiKeyResponse {
  raw_key: string;
}

export interface BudgetResponse {
  id: string;
  amount_usd: string;
  period: string;
  action: string;
  is_active: boolean;
  created_at: string;
}

export interface AlertChannel {
  type: string;
  target: string;
}

export interface AlertResponse {
  id: string;
  name: string;
  metric: string;
  condition: string;
  threshold: string;
  window_minutes: number;
  channels: AlertChannel[];
  is_active: boolean;
  created_at: string;
}

export const settings = {
  // API Keys
  listApiKeys: (projectId: string, token: string) =>
    request<ApiKeyResponse[]>(`/v1/projects/${projectId}/api-keys`, { token }),

  createApiKey: (
    projectId: string,
    body: { name: string; environment: string },
    token: string,
  ) =>
    request<ApiKeyCreatedResponse>(`/v1/projects/${projectId}/api-keys`, {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),

  deleteApiKey: (projectId: string, keyId: string, token: string) =>
    request<void>(`/v1/projects/${projectId}/api-keys/${keyId}`, {
      method: "DELETE",
      token,
    }),

  // Budgets
  listBudgets: (projectId: string, token: string) =>
    request<BudgetResponse[]>(`/v1/projects/${projectId}/budgets`, { token }),

  createBudget: (
    projectId: string,
    body: { amount_usd: string; period: string; action?: string },
    token: string,
  ) =>
    request<BudgetResponse>(`/v1/projects/${projectId}/budgets`, {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),

  deleteBudget: (projectId: string, budgetId: string, token: string) =>
    request<void>(`/v1/projects/${projectId}/budgets/${budgetId}`, {
      method: "DELETE",
      token,
    }),

  // Alerts
  listAlerts: (projectId: string, token: string) =>
    request<AlertResponse[]>(`/v1/projects/${projectId}/alerts`, { token }),

  createAlert: (
    projectId: string,
    body: {
      name: string;
      metric: string;
      condition: string;
      threshold: string;
      window_minutes?: number;
      channels?: AlertChannel[];
    },
    token: string,
  ) =>
    request<AlertResponse>(`/v1/projects/${projectId}/alerts`, {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),

  toggleAlert: (
    projectId: string,
    alertId: string,
    is_active: boolean,
    token: string,
  ) =>
    request<AlertResponse>(`/v1/projects/${projectId}/alerts/${alertId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active }),
      token,
    }),

  deleteAlert: (projectId: string, alertId: string, token: string) =>
    request<void>(`/v1/projects/${projectId}/alerts/${alertId}`, {
      method: "DELETE",
      token,
    }),

  testAlert: (projectId: string, alertId: string, token: string) =>
    request<void>(`/v1/projects/${projectId}/alerts/${alertId}/test`, {
      method: "POST",
      token,
    }),
};

// ── Admin ─────────────────────────────────────────────────────────────────────

export interface AdminProjectRow {
  org_id: string;
  org_name: string;
  project_id: string;
  project_name: string;
  project_slug: string;
  created_at: string;
  span_count: number;
  total_cost_usd: number;
  last_active_at: string | null;
}

export interface CreateClientResponse {
  org_id: string;
  org_name: string;
  project_id: string;
  project_name: string;
  api_key: string;
}

export const admin = {
  listProjects: (token: string) =>
    request<AdminProjectRow[]>("/api/v1/admin/projects", { token }),

  createClient: (
    body: { org_name: string; project_name: string },
    token: string,
  ) =>
    request<CreateClientResponse>("/api/v1/admin/clients", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
};

// ── Projects ──────────────────────────────────────────────────────────────────

export interface ProjectResponse {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  description: string | null;
  upstream_base_url: string | null;
  upstream_provider: string | null;
  created_at: string;
}

export const projects = {
  list: (token: string) =>
    request<ProjectResponse[]>("/v1/projects", { token }),

  create: (
    body: { name: string; description?: string; upstream_base_url?: string },
    token: string,
  ) =>
    request<ProjectResponse>("/v1/projects", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),

  setUpstream: (projectId: string, baseUrl: string, token: string) =>
    request<ProjectResponse>(`/v1/projects/${projectId}/upstream`, {
      method: "PATCH",
      body: JSON.stringify({ base_url: baseUrl }),
      token,
    }),
};

// ── Insights ──────────────────────────────────────────────────────────────────

export type InsightType = "cost_forecast" | "rate_limit_eta" | "model_drift";
export type InsightSeverity = "info" | "warning" | "critical";
export type InsightStatus = "open" | "acknowledged" | "resolved";

export interface Insight {
  id: string;
  type: InsightType;
  severity: InsightSeverity;
  status: InsightStatus;
  title: string;
  summary: string;
  detail: Record<string, unknown>;
  confidence: number | null;
  predicted_for: string | null;
  created_at: string;
  updated_at: string;
}

export interface InsightListResponse {
  insights: Insight[];
  count: number;
}

export const insights = {
  list: (
    projectId: string,
    opts: { status?: InsightStatus | "all"; type?: InsightType },
    token: string,
  ) => {
    const params = new URLSearchParams();
    if (opts.status) params.set("status", opts.status);
    if (opts.type) params.set("type", opts.type);
    const qs = params.toString();
    return request<InsightListResponse>(
      `/v1/projects/${projectId}/insights${qs ? `?${qs}` : ""}`,
      { token },
    );
  },

  updateStatus: (insightId: string, status: InsightStatus, token: string) =>
    request<{ id: string; status: InsightStatus }>(`/v1/insights/${insightId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
      token,
    }),
};

// ── SSE live feed ─────────────────────────────────────────────────────────────

export function createLiveFeed(projectId: string, token: string) {
  const url = `${API_URL}/v1/projects/${projectId}/metrics/live`;
  // EventSource doesn't support custom headers — send token as query param
  return new EventSource(`${url}?token=${encodeURIComponent(token)}`);
}
