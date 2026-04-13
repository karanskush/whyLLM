export interface LLMDawgConfig {
  apiKey: string;
  baseUrl?: string;
  /** Timeout in milliseconds for ingest calls. Default: 5000 */
  timeout?: number;
}

export interface SpanData {
  name?: string;
  kind: "llm_call" | "retrieval" | "tool_call" | "custom";
  provider: string;
  model: string;
  inputTokens?: number;
  outputTokens?: number;
  cachedTokens?: number;
  latencyMs?: number;
  ttftMs?: number;
  status: "success" | "error" | "timeout" | "cancelled";
  errorType?: string;
  errorMessage?: string;
  request?: Record<string, unknown>;
  response?: Record<string, unknown>;
  userId?: string;
  sessionId?: string;
  tags?: Record<string, string>;
  startedAt?: string;
  endedAt?: string;
}
