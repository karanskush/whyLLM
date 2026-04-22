import { whyllmClient } from "./client";
import type { whyllmConfig } from "./types";

let _client: whyllmClient | null = null;

/** Initialize the global whyllm tracer. Call once at startup. */
export function init(config: whyllmConfig): whyllmClient {
  _client = new whyllmClient(config);
  return _client;
}

/** Return the current client, throwing if init() was not called. */
export function getClient(): whyllmClient {
  if (!_client) {
    throw new Error("whyllm: call init() before using wrap() or getClient()");
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
