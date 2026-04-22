/**
 * whyllm JS/TS SDK
 *
 * @example
 * ```ts
 * import { init, wrap } from "@whyllm/sdk";
 * import OpenAI from "openai";
 *
 * init({ apiKey: "ld-proj-..." });
 * const openai = wrap(new OpenAI());
 * const response = await openai.chat.completions.create({ ... }); // auto-traced
 * ```
 */

export { whyllmClient } from "./client";
export { init, wrap } from "./tracer";
export type { whyllmConfig, SpanData } from "./types";
