/** Dashboard metrics (SPEC 11.1). `/metrics/summary` also feeds the top bar's spend / budget. */
import { z } from "zod";

import { MessageSchema, PriceSchema, Timestamp, WhereSchema } from "@/api/schemas/common";
import { EpisodeStageSchema } from "@/api/schemas/episodes";
import { QaIssueSchema } from "@/api/schemas/products";

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

/** `/metrics/shots`: the dashboard's shot state (derived from products, not the shot table). */
export const ShotMetricStatusSchema = z.enum([
  "adopted",
  "picking",
  "generating",
  "queued",
  "waiting",
]);
export type ShotMetricStatus = z.infer<typeof ShotMetricStatusSchema>;

/** Compute stages of a shot, in bar order: keyframe, video generation, QA and upscaling. */
export const ShotStageSchema = z.enum(["kf", "vid", "post"]);
export type ShotStage = z.infer<typeof ShotStageSchema>;
export const SHOT_STAGES = ShotStageSchema.options;

export const ShotMetricSchema = z.object({
  shot_id: z.string(),
  scene: z.number().int(),
  /** Shot description (user content). */
  title: z.string(),
  /** Σ(finished − started) per stage, seconds. */
  stage_seconds: z.record(ShotStageSchema, z.number()),
  cost_usd: z.number(),
  takes: z.number().int(),
  status: ShotMetricStatusSchema,
  /** `waiting`: the upstream shot whose last frame this one starts from. */
  waiting_for: z.string().nullable(),
  /** What happened, sentence by sentence (`dashboard.shots.note.<code>`). */
  notes: z.array(MessageSchema),
  /** The takes in order (`dashboard.shots.take.<code>`), shown joined with arrows. */
  take_chain: z.array(MessageSchema),
});
export type ShotMetric = z.infer<typeof ShotMetricSchema>;

export const ShotMetricsSchema = z.object({
  scenes: z.array(z.object({ scene: z.number().int(), title: z.string() })),
  shots: z.array(ShotMetricSchema),
});
export type ShotMetrics = z.infer<typeof ShotMetricsSchema>;

/** `/metrics/components`: accumulated compute per component, local vs waiting on an API. */
export const ComponentMetricsSchema = z.object({
  rows: z.array(
    z.object({
      /** components.yaml id. */
      component: z.string(),
      local_seconds: z.number(),
      api_seconds: z.number(),
    }),
  ),
});
export type ComponentMetrics = z.infer<typeof ComponentMetricsSchema>;

/** `/metrics/speed`: seconds of compute per second of output, per video model and place. */
export const SpeedMetricsSchema = z.object({
  /** The typical shot length the "4 秒约 7.5 分钟" example uses. */
  example_output_s: z.number(),
  rows: z.array(
    z.object({
      model: z.string(),
      where: WhereSchema,
      price: PriceSchema.nullable(),
      median: z.number(),
      min: z.number(),
      max: z.number(),
      samples: z.number().int(),
    }),
  ),
  notes: z.array(MessageSchema),
});
export type SpeedMetrics = z.infer<typeof SpeedMetricsSchema>;

/** `/metrics/apis`: one row per API model, sorted by cost (highest first). */
export const ApiMetricsSchema = z.object({
  rows: z.array(
    z.object({
      model: z.string(),
      kind: CallKindSchema,
      calls: z.number().int(),
      succeeded: z.number().int(),
      canceled: z.number().int(),
      median_latency_s: z.number(),
      /** Usage in words (`dashboard.apis.usage.<code>`). */
      usage: MessageSchema,
      prices: z.array(PriceSchema),
      cost_usd: z.number(),
      note: MessageSchema.nullable(),
    }),
  ),
  total_cost_usd: z.number(),
});
export type ApiMetrics = z.infer<typeof ApiMetricsSchema>;

/** `/metrics/local-models`: runs, time and VRAM peak per local model. */
export const LocalModelMetricsSchema = z.object({
  /** The machine's VRAM: a full bar. */
  vram_total_gb: z.number(),
  rows: z.array(
    z.object({
      model: z.string(),
      components: z.array(z.string()),
      runs: z.number().int(),
      seconds: z.number(),
      vram_peak_gb: z.number(),
    }),
  ),
  notes: z.array(MessageSchema),
});
export type LocalModelMetrics = z.infer<typeof LocalModelMetricsSchema>;

/** `/metrics/qa`: auto QA of video takes. A failed take can have several issues. */
export const QaMetricsSchema = z.object({
  passed: z.number().int(),
  failed: z.number().int(),
  issues: z.array(z.object({ issue: QaIssueSchema, count: z.number().int() })),
  auto_reruns: z.number().int(),
  auto_fallbacks: z.number().int(),
  manual_switches: z.number().int(),
});
export type QaMetrics = z.infer<typeof QaMetricsSchema>;

/** `/metrics/episodes`: per-episode progress and money; not-started ones are estimates. */
export const EpisodeMetricsSchema = z.object({
  rows: z.array(
    z.object({
      episode_id: z.string(),
      idx: z.number().int(),
      title: z.string(),
      stage: EpisodeStageSchema,
      adopted_seconds: z.number(),
      total_seconds: z.number(),
      /** `total_seconds` is the planned target, not yet a sum of shots. */
      total_estimated: z.boolean(),
      spent_usd: z.number(),
      projected_usd: z.number(),
      /** The projection is lower because locked assets are reused. */
      reuses_assets: z.boolean(),
      compute_seconds: z.number().nullable(),
    }),
  ),
});
export type EpisodeMetrics = z.infer<typeof EpisodeMetricsSchema>;
