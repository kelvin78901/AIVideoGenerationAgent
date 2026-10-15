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
  fallback_from_job_id: z.string().nullable(),
  created_at: Timestamp,
  started_at: Timestamp.nullable(),
  finished_at: Timestamp.nullable(),
});
export type Job = z.infer<typeof JobSchema>;

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
