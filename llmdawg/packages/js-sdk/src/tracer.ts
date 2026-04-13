import { LLMDawgClient } from "./client";
import type { LLMDawgConfig } from "./types";

let _client: LLMDawgClient | null = null;

/** Initialize the global LLMDawg tracer. Call once at startup. */
export function init(config: LLMDawgConfig): LLMDawgClient {
  _client = new LLMDawgClient(config);
  return _client;
}

/** Return the current client, throwing if init() was not called. */
export function getClient(): LLMDawgClient {
  if (!_client) {
    throw new Error("LLMDawg: call init() before using wrap() or getClient()");
  }
  return _client;
}

/**
 * Wrap a provider client to automatically trace all LLM calls.
 * Phase 1 stub — full implementation in Phase 2.
 */
export function wrap<T>(client: T): T {
  // TODO(phase-2): detect provider and patch methods
  return client;
}
