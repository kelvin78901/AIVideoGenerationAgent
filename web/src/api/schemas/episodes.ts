/** Episodes and per-step progress (SPEC 4.1; `GET /series/{id}/episodes`, `GET /episodes/{id}/progress`). */
import { z } from "zod";

export const EpisodeStageSchema = z.enum(["in_progress", "script_pending", "not_started", "done"]);
export type EpisodeStage = z.infer<typeof EpisodeStageSchema>;

export const EpisodeSchema = z.object({
  id: z.string(),
  series_id: z.string(),
  /** 1-based number within the series; the route uses it (`/s/:series/e/:idx/...`). */
  idx: z.number().int().positive(),
  title: z.string(),
  hook: z.string().nullable(),
  cliffhanger: z.string().nullable(),
  target_seconds: z.number().nullable(),
  budget_usd: z.number().nullable(),
  stage: EpisodeStageSchema,
  /** Scenes the episode covers (场 1–2); null before episode planning. */
  scene_from: z.number().int().nullable(),
  scene_to: z.number().int().nullable(),
  /** Shots once the storyboard exists. */
  shot_count: z.number().int().nullable(),
  script_status: z.enum(["none", "draft", "confirmed"]),
});
export type Episode = z.infer<typeof EpisodeSchema>;

/** `PATCH /episodes/{id}`: the fields the UI edits so far. */
export const EpisodePatchSchema = z.object({
  budget_usd: z.number().nonnegative().nullable().optional(),
});
export type EpisodePatch = z.infer<typeof EpisodePatchSchema>;

export const STEP_IDS = ["novel", "script", "assets", "storyboard", "generate", "post"] as const;
export const StepIdSchema = z.enum(STEP_IDS);
export type StepId = z.infer<typeof StepIdSchema>;

/** One production step as the nav badge shows it: 已确认 / 7/13 / 未开始 / 待更新 N. */
export const StepProgressSchema = z.object({
  state: z.enum(["confirmed", "in_progress", "not_started"]),
  done: z.number().int().nullable(),
  total: z.number().int().nullable(),
  /** Products marked stale by invalidation (待更新). */
  stale: z.number().int(),
});
export type StepProgress = z.infer<typeof StepProgressSchema>;

export const EpisodeProgressSchema = z.object({
  episode_id: z.string(),
  steps: z.record(StepIdSchema, StepProgressSchema),
});
export type EpisodeProgress = z.infer<typeof EpisodeProgressSchema>;
