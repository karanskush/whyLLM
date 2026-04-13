/**
 * LLMDawg JS/TS SDK
 *
 * @example
 * ```ts
 * import { init, wrap } from "@llmdawg/sdk";
 * import OpenAI from "openai";
 *
 * init({ apiKey: "ld-proj-..." });
 * const openai = wrap(new OpenAI());
 * const response = await openai.chat.completions.create({ ... }); // auto-traced
 * ```
 */

export { LLMDawgClient } from "./client";
export { init, wrap } from "./tracer";
export type { LLMDawgConfig, SpanData } from "./types";
