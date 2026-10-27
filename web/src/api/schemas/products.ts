/**
 * Products and versions (SPEC 4.2): every card with the four buttons (改提示词 / 重跑 /
 * 不满意换一个 / 历史) is a product; each run or edit appends a version, never overwrites.
 */
import { z } from "zod";

import { Timestamp, WhereSchema } from "@/api/schemas/common";

export const OwnerTypeSchema = z.enum(["series", "episode", "scene", "shot", "asset", "line"]);
export type OwnerType = z.infer<typeof OwnerTypeSchema>;

export const ProductSlotSchema = z.enum([
  // The imported novel: one `import` version per import (DECISIONS 2026-10-19 · M2 step 5).
  "novel",
  "bible",
  "suggestions",
  "episodes",
  "script",
  "asset_list",
  "ref_image",
  // A character's side / back / expression views, made from the locked reference (M3).
  "ref_views",
  "text_image",
  "voice",
  "line_audio",
  "shot_plan",
  "keyframe",
  "video",
  "upscale",
  "lipsync",
  "qa",
  "music",
  "sfx",
  "subtitles",
  "cut",
]);
export type ProductSlot = z.infer<typeof ProductSlotSchema>;

export const ProductStatusSchema = z.enum([
  "empty",
  "queued",
  "running",
  "ready",
  "stale",
  "adopted",
  "locked",
  "failed",
]);
export type ProductStatus = z.infer<typeof ProductStatusSchema>;

export const VersionOriginSchema = z.enum([
  "run",
  "rerun",
  "switch",
  "edit",
  "fallback",
  "import",
  "auto_qa_rerun",
  "comfy_ingest",
  /** The candidate the user locked, alone (M3). */
  "pick",
  /** The user's own file (M3: a reference picture). */
  "upload",
]);
export type VersionOrigin = z.infer<typeof VersionOriginSchema>;

export const VersionFileSchema = z.object({
  role: z.string(),
  path: z.string(),
  sha256: z.string(),
  mime: z.string(),
  duration_s: z.number().nullable(),
  w: z.number().int().nullable(),
  h: z.number().int().nullable(),
  /** A candidate's or view's number in its version (0-based; M3). */
  idx: z.number().int().nullable().optional(),
  /** Which view a `role: view` picture is: side / back / calm / smile / angry / sad (M3 补视图;
   * versions before 2026-10-21 have one `expressions` sheet instead of the four). */
  view: z.string().nullable().optional(),
  /** A voice sample: which of the voice's audition lines it reads. */
  line: z.number().int().nullable().optional(),
  /** A voice's emotion variant (`enums:emotion.<id>`, config/voice.yaml). */
  emotion: z.string().nullable().optional(),
  /** Audio: 64 peaks, 0–1, measured by the backend. */
  waveform: z.array(z.number()).nullable().optional(),
});
export type VersionFile = z.infer<typeof VersionFileSchema>;

/**
 * Auto QA of a video take (SPEC 5 `qa`, components.yaml thresholds): face similarity to the
 * locked reference, SyncNet confidence, ASR character error rate, OCR of on-screen text, and
 * the vision model's look at the picture.
 */
export const QaMetricSchema = z.enum(["face", "lipsync", "asr", "ocr", "vlm"]);
export type QaMetric = z.infer<typeof QaMetricSchema>;

/** What the vision model or OCR found; the UI translates `enums:qaIssue.<code>`. */
export const QaIssueSchema = z.enum([
  "face_mismatch",
  "finger_fusion",
  "color_off",
  "light_missing",
  "text_mismatch",
]);
export type QaIssue = z.infer<typeof QaIssueSchema>;

export const QaCheckSchema = z.object({
  metric: QaMetricSchema,
  /** Score (face 0–1, lipsync confidence, asr error ratio); null for ocr / vlm and n/a. */
  value: z.number().nullable(),
  /** OCR: the characters read off the picture (content). */
  text: z.string().nullable(),
  issue: QaIssueSchema.nullable(),
  /** null = does not apply to this shot (no dialogue, no on-screen text …). */
  ok: z.boolean().nullable(),
});
export type QaCheck = z.infer<typeof QaCheckSchema>;

export const QaResultSchema = z.object({
  checks: z.array(QaCheckSchema),
  /** Total used to recommend a take: the highest passing score (SPEC 4.2). */
  score: z.number(),
});
export type QaResult = z.infer<typeof QaResultSchema>;

/** Why a version came from a fallback (`model_call.fallback_reason`). */
export const FallbackReasonSchema = z.enum(["error", "timeout", "qa_fail"]);
export type FallbackReason = z.infer<typeof FallbackReasonSchema>;

export const ProductVersionSchema = z.object({
  id: z.string(),
  product_id: z.string(),
  /** 1-based, shown as "v{n}". */
  n: z.number().int().positive(),
  origin: VersionOriginSchema,
  parent_version_id: z.string().nullable(),
  payload: z.record(z.string(), z.unknown()),
  files: z.array(VersionFileSchema),
  content_hash: z.string().nullable(),
  /** Intent layer (the user's words) and the compiled prompt actually sent (SPEC 8). */
  intent: z.string().nullable(),
  compiled: z.string().nullable(),
  compiled_overridden: z.boolean(),
  model_key: z.string().nullable(),
  where: WhereSchema.nullable(),
  seed: z.number().int().nullable(),
  params: z.record(z.string(), z.unknown()),
  qa: QaResultSchema.nullable(),
  qa_pass: z.boolean().nullable(),
  /** origin=fallback: what triggered it. */
  fallback_reason: FallbackReasonSchema.nullable(),
  /** Hybrid mode: a free local draft or the API final made before adopting (SPEC 7.3). */
  stage: z.enum(["draft", "final"]).nullable(),
  /** The user's 1–5 score on the take wall (number keys); null = not rated. */
  rating: z.number().int().min(1).max(5).nullable(),
  /** Billed API cost; 0 for local runs. */
  cost_usd: z.number(),
  job_id: z.string().nullable(),
  created_at: Timestamp,
  /** Free-text note from the user; the UI labels the origin itself. */
  note: z.string().nullable(),
});
export type ProductVersion = z.infer<typeof ProductVersionSchema>;

/** The prompt the next run will use: saved by 「只保存」 or by a run (SPEC 7.4). */
export const ProductPromptSchema = z.object({
  intent: z.string(),
  compiled: z.string(),
  /** The compiled layer was edited by hand; it no longer follows the intent. */
  compiled_overridden: z.boolean(),
  /** Model the compiled layer was built for. */
  model_key: z.string(),
});
export type ProductPrompt = z.infer<typeof ProductPromptSchema>;

/** `estimate()` for the next rerun on the current route (hard rule 6: price before spending). */
export const RunEstimateSchema = z.object({
  model_key: z.string(),
  where: WhereSchema,
  cost_usd: z.number(),
  seconds: z.number().nullable(),
  /** False: the model has no known price (`cost_usd` is 0); a run asks first. */
  priced: z.boolean().optional(),
});
export type RunEstimate = z.infer<typeof RunEstimateSchema>;

export const ProductSchema = z.object({
  id: z.string(),
  series_id: z.string(),
  owner_type: OwnerTypeSchema,
  owner_id: z.string(),
  slot: ProductSlotSchema,
  component_id: z.string(),
  current_version_id: z.string().nullable(),
  adopted_version_id: z.string().nullable(),
  locked_hash: z.string().nullable(),
  status: ProductStatusSchema,
  /** Oldest first. */
  versions: z.array(ProductVersionSchema),
  prompt: ProductPromptSchema.nullable(),
  estimate: RunEstimateSchema.nullable(),
  /** The job producing the next version while status is queued / running. */
  running: z
    .object({
      job_id: z.string(),
      model_key: z.string(),
      /** `waiting_confirm`: over a spending limit or an ask-first fallback (ConfirmJobs). */
      state: z.enum(["queued", "waiting_confirm", "running"]).optional(),
      /** The 确认并同步 this run is part of (「同步中」); null for a run of its own. */
      cascade_id: z.string().nullable().optional(),
    })
    .nullable(),
  /** 「选这个」: candidate `idx` (its `files[].idx`) of version `version_id` (M3). */
  pick: z.object({ version_id: z.string(), idx: z.number().int().nonnegative() }).nullish(),
  /** Its owner left (a script line a rerun dropped): never stale, not counted. */
  retired: z.boolean().optional(),
});
export type Product = z.infer<typeof ProductSchema>;

export const RunModeSchema = z.enum(["run", "rerun", "switch"]);
export type RunMode = z.infer<typeof RunModeSchema>;

/** `POST /products/{id}/run` → Job. `intent` / `compiled` come from 「保存并重跑」. */
export const RunRequestSchema = z.object({
  mode: RunModeSchema,
  model: z.string().optional(),
  intent: z.string().optional(),
  /** Hand-edited compiled layer; omitted = compile from the intent. */
  compiled: z.string().optional(),
  /** Takes to generate (生成页「再出一条」); default 1. */
  count: z.number().int().positive().optional(),
  /** `api`: hybrid mode's 「用 API 出终版」 (SPEC 7.3). */
  where: WhereSchema.optional(),
  /** What the component reads besides the prompt (M3): a task, the draft a final starts from. */
  params: z
    .object({
      task: z.string().optional(),
      source_version_id: z.string().optional(),
      source_idx: z.number().int().nonnegative().optional(),
    })
    .optional(),
});
export type RunRequest = z.infer<typeof RunRequestSchema>;

/** `PUT /products/{id}/prompt` (「只保存」); `compiled: null` = compile automatically. */
export const SavePromptRequestSchema = z.object({
  intent: z.string(),
  compiled: z.string().nullable(),
});
export type SavePromptRequest = z.infer<typeof SavePromptRequestSchema>;

/** `POST /products/{id}/compile` → preview of the compiled layer for an intent. */
export const CompileRequestSchema = z.object({
  intent: z.string(),
  model: z.string().optional(),
});
export const CompileResultSchema = z.object({ compiled: z.string(), model_key: z.string() });
export type CompileResult = z.infer<typeof CompileResultSchema>;

/** `PATCH /versions/{id}` */
export const VersionPatchSchema = z.object({ rating: z.number().int().min(1).max(5).nullable() });
export type VersionPatch = z.infer<typeof VersionPatchSchema>;

/**
 * Payload of the `version.created` event: just enough to refetch. The version itself (its
 * payload can be a whole script) is read with `GET /products/{id}`.
 */
export const VersionCreatedEventSchema = z.object({
  product_id: z.string(),
  version_id: z.string(),
  n: z.number().int().positive(),
  origin: VersionOriginSchema,
});

/** Payload of the `product.updated` event. */
export const ProductUpdatedEventSchema = z.object({
  product_id: z.string(),
  series_id: z.string(),
  status: ProductStatusSchema,
});
