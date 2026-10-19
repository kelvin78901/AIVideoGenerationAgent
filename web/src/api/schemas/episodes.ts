/**
 * Episodes, their beats and per-step progress (SPEC 4.1; `GET /series/{id}/episodes`,
 * `PATCH /episodes/{id}`, `PATCH /beats/{id}`, `GET /episodes/{id}/progress`). The list is the
 * adopted 分集规划 (backend `episodes/schema.py`).
 */
import { z } from "zod";

import { SourceSpanSchema } from "@/api/schemas/novel";

export const EpisodeStageSchema = z.enum(["in_progress", "script_pending", "not_started", "done"]);
export type EpisodeStage = z.infer<typeof EpisodeStageSchema>;

/** One beat of an episode's plan (节拍看板, 情绪曲线). */
export const BeatSchema = z.object({
  id: z.string(),
  episode_id: z.string(),
  /** 1-based within the episode. */
  idx: z.number().int().positive(),
  text: z.string(),
  /** -1 (lowest) … 1 (highest). */
  emotion: z.number().min(-1).max(1),
  /** Paragraph numbers across the book, 0-based. */
  paras: z.array(z.number().int()),
  source_spans: z.array(SourceSpanSchema),
});
export type Beat = z.infer<typeof BeatSchema>;

export const EpisodeSchema = z.object({
  id: z.string(),
  series_id: z.string(),
  /** 1-based number within the series; the route uses it (`/s/:series/e/:idx/...`). */
  idx: z.number().int().positive(),
  title: z.string(),
  hook: z.string().nullable(),
  cliffhanger: z.string().nullable(),
  target_seconds: z.number().nullable(),
  /** 预计场数 from the plan. */
  scene_count: z.number().int().nullable(),
  budget_usd: z.number().nullable(),
  stage: EpisodeStageSchema,
  /** Scenes the episode covers (场 1–2), numbered across the series (planned before the script). */
  scene_from: z.number().int().nullable(),
  scene_to: z.number().int().nullable(),
  /** Shots once the storyboard exists. */
  shot_count: z.number().int().nullable(),
  script_status: z.enum(["none", "draft", "confirmed"]),
  beats: z.array(BeatSchema),
});
export type Episode = z.infer<typeof EpisodeSchema>;

/**
 * `PATCH /episodes/{id}`: only the fields sent change. The budget is a setting; the others edit
 * the plan (an adopted `edit` version of 分集规划).
 */
export const EpisodePatchSchema = z.object({
  title: z.string().max(200).optional(),
  hook: z.string().max(500).optional(),
  cliffhanger: z.string().max(500).optional(),
  target_seconds: z.number().int().positive().optional(),
  budget_usd: z.number().nonnegative().nullable().optional(),
});
export type EpisodePatch = z.infer<typeof EpisodePatchSchema>;

/**
 * `PATCH /beats/{id}`: 改文字、情绪, or drag it (`position`: 0-based among the target episode's
 * other beats; the end when omitted). Answers the whole plan.
 */
export const BeatPatchSchema = z.object({
  text: z.string().max(500).optional(),
  emotion: z.number().min(-1).max(1).optional(),
  episode_id: z.string().optional(),
  position: z.number().int().nonnegative().optional(),
});
export type BeatPatch = z.infer<typeof BeatPatchSchema>;

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
