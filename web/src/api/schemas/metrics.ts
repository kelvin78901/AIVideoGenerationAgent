/** Dashboard metrics (SPEC 11.1). `/metrics/summary` also feeds the top bar's spend / budget. */
import { z } from "zod";

import { MessageSchema, Timestamp } from "@/api/schemas/common";

export const MetricsScopeSchema = z.enum(["episode", "series"]);
export type MetricsScope = z.infer<typeof MetricsScopeSchema>;

export const MetricsSummarySchema = z.object({
  scope: MetricsScopeSchema,
  /** Σ billed `model_call.cost_usd`. */
  spent_usd: z.number(),
  budget_usd: z.number().nullable(),
  /** Spent + remaining products × current-route estimate. */
  projected_usd: z.number(),
  /** 「值得注意」: sentences the UI renders from `dashboard.insight.<code>`. */
  insights: z.array(MessageSchema),
  updated_at: z.string(),
});
export type MetricsSummary = z.infer<typeof MetricsSummarySchema>;

/** `/metrics/kpis`: the six tiles under the budget card. Durations are seconds. */
export const MetricsKpisSchema = z.object({
  scope: MetricsScopeSchema,
  /** Σ duration of adopted takes / Σ planned shot duration. */
  adopted_seconds: z.number(),
  total_seconds: z.number(),
  shots: z.number().int(),
  shots_adopted: z.number().int(),
  /** Spent / adopted seconds; null before anything is adopted. */
  cost_per_second_usd: z.number().nullable(),
  /** Projected / total seconds once one-off assets are spread over the episode. */
  projected_cost_per_second_usd: z.number().nullable(),
  local_gpu_seconds: z.number(),
  /** Time spent waiting on API calls (started → finished). */
  api_wait_seconds: z.number(),
  vram_peak_gb: z.number().nullable(),
  api_calls: z.number().int(),
  api_succeeded: z.number().int(),
  api_canceled: z.number().int(),
  /** Calls that hit a rate limit and were retried automatically. */
  rate_limit_retries: z.number().int(),
  qa_passed: z.number().int(),
  qa_total: z.number().int(),
  auto_reruns: z.number().int(),
  auto_fallbacks: z.number().int(),
  manual_switches: z.number().int(),
  /** Median time from a shot's first run to its adopted take; null before any adoption. */
  adopt_median_seconds: z.number().nullable(),
  /** The longest-running shot that has no adopted take yet. */
  slowest_open: z.object({ shot: z.string(), seconds: z.number() }).nullable(),
});
export type MetricsKpis = z.infer<typeof MetricsKpisSchema>;

/** One 15-minute bucket of `/metrics/spend-series`. */
export const SpendBucketSchema = z.object({
  start: Timestamp,
  /** The last bucket ends at "now". */
  end: Timestamp,
  add_usd: z.number(),
  cum_usd: z.number(),
  /** 「花在哪」: phrases from `dashboard.spend.item.<code>`, joined with " · ". */
  items: z.array(MessageSchema),
});
export type SpendBucket = z.infer<typeof SpendBucketSchema>;

export const SpendSeriesSchema = z.object({
  scope: MetricsScopeSchema,
  bucket_minutes: z.number().int(),
  /** The x axis runs from `start` to `end`; the projection is drawn from `now` to `end`. */
  start: Timestamp,
  now: Timestamp,
  end: Timestamp,
  buckets: z.array(SpendBucketSchema),
  projected_usd: z.number(),
  budget_usd: z.number().nullable(),
});
export type SpendSeries = z.infer<typeof SpendSeriesSchema>;

/** Call categories, mapped from the model kind (SPEC 11.1). Fixed order: text, image, av. */
export const CallKindSchema = z.enum(["text", "image", "av"]);
export type CallKind = z.infer<typeof CallKindSchema>;
export const CALL_KINDS = CallKindSchema.options;

export const CallsBucketSchema = z.object({
  start: Timestamp,
  end: Timestamp,
  counts: z.record(CallKindSchema, z.number().int()),
  failed: z.number().int(),
  cost_usd: z.number(),
});
export type CallsBucket = z.infer<typeof CallsBucketSchema>;

export const CallsSeriesSchema = z.object({
  scope: MetricsScopeSchema,
  bucket_minutes: z.number().int(),
  buckets: z.array(CallsBucketSchema),
  totals: z.array(
    z.object({ kind: CallKindSchema, calls: z.number().int(), cost_usd: z.number() }),
  ),
  calls: z.number().int(),
  succeeded: z.number().int(),
});
export type CallsSeries = z.infer<typeof CallsSeriesSchema>;
