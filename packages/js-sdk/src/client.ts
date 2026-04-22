import type { whyllmConfig, SpanData } from "./types";

export class whyllmClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeout: number;

  constructor(config: whyllmConfig) {
    this.apiKey = config.apiKey;
    this.baseUrl = (config.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.timeout = config.timeout ?? 5000;
  }

  /** Fire-and-forget span ingest. Never throws — observability must not break the app. */
  async ingestSpan(span: SpanData): Promise<void> {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeout);
      await fetch(`${this.baseUrl}/v1/ingest/spans`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-whyllm-Key": this.apiKey,
        },
        body: JSON.stringify(span),
        signal: controller.signal,
      });
      clearTimeout(timer);
    } catch {
      // Intentionally silent — never let observability break the caller
    }
  }
}
