/** Jobs, model calls and health: `job_public`, `call_public` and `/health` in the Python code. */
import { z } from "zod";

import { ApiErrorBodySchema, Timestamp, WhereSchema } from "@/api/schemas/common";

export const JobStateSchema = z.enum([
  "queued",
  "waiting_confirm",
  "running",
  "succeeded",
  "failed",
  "canceled",
]);
export type JobState = z.infer<typeof JobStateSchema>;

export const JobSchema = z.object({
  id: z.string(),
  series_id: z.string().nullable(),
  /** The episode its spending counts against (SPEC 7.6); null for series-level work. */
  episode_id: z.string().nullable().optional(),
  product_id: z.string().nullable(),
  component_id: z.string().nullable(),
  kind: z.string(),
  queue: z.string(),
  state: JobStateSchema,
  priority: z.number(),
  attempt: z.number(),
  max_attempts: z.number(),
  params: z.record(z.string(), z.unknown()),
  result: z.record(z.string(), z.unknown()).nullable(),
  error: ApiErrorBodySchema.nullable(),
  depends_on: z.array(z.string()),
  est_cost_usd: z.number().nullable(),
  /** What the user agreed to spend when confirming it. */
  confirmed_usd: z.number().nullable().optional(),
  fallback_from_job_id: z.string().nullable(),
  created_at: Timestamp,
  started_at: Timestamp.nullable(),
  finished_at: Timestamp.nullable(),
  /** Only on `job.updated` while it runs, e.g. ComfyUI's sampler steps (`step`, `steps`, `pct`). */
  progress: z.record(z.string(), z.unknown()).optional(),
});
export type Job = z.infer<typeof JobSchema>;

/**
 * Why a `product.run` job waits for a yes (`params.confirm`): over the component's per-call
 * cap, over what is left of the shot's cap (generate rules) or of the episode budget, a model
 * without a known price, or a fallback set to ask first (`priced` false: the fallback model has no known price).
 */
export const JobConfirmSchema = z.object({
  reason: z.enum(["per_call", "shot", "episode", "unpriced", "fallback"]),
  estimate_usd: z.number(),
  limit_usd: z.number().nullable(),
  failed_model: z.string().optional(),
  error: z.string().optional(),
  priced: z.boolean().optional(),
});
export type JobConfirm = z.infer<typeof JobConfirmSchema>;

export const ModelCallSchema = z.object({
  id: z.number(),
  job_id: z.string().nullable(),
  component_id: z.string().nullable(),
  provider_id: z.string().nullable(),
  model_key: z.string(),
  where: WhereSchema,
  is_fallback: z.boolean(),
  fallback_reason: z.string().nullable(),
  status: z.enum(["success", "error", "timeout", "canceled"]),
  error_code: z.string().nullable(),
  tokens_in: z.number().nullable(),
  tokens_out: z.number().nullable(),
  cost_usd: z.number(),
  billed: z.boolean(),
  started_at: Timestamp.nullable(),
  finished_at: Timestamp.nullable(),
});
export type ModelCall = z.infer<typeof ModelCallSchema>;

export const HealthSchema = z.object({
  status: z.string(),
  version: z.string(),
  /** True unless the backend runs with DRAMA_MOCK=0. */
  mock: z.boolean(),
});
export type Health = z.infer<typeof HealthSchema>;
