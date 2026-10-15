/**
 * Products and versions (SPEC 4.2): every card with the four buttons (改提示词 / 重跑 /
 * 不满意换一个 / 历史) is a product; each run or edit appends a version, never overwrites.
 */
import { z } from "zod";

import { Timestamp, WhereSchema } from "@/api/schemas/common";

export const OwnerTypeSchema = z.enum(["series", "episode", "scene", "shot", "asset", "line"]);
export type OwnerType = z.infer<typeof OwnerTypeSchema>;

export const ProductSlotSchema = z.enum([
  "bible",
  "suggestions",
  "episodes",
  "script",
  "asset_list",
  "ref_image",
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
});
export type VersionFile = z.infer<typeof VersionFileSchema>;

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
  qa: z.record(z.string(), z.unknown()).nullable(),
  qa_pass: z.boolean().nullable(),
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
  running: z.object({ job_id: z.string(), model_key: z.string() }).nullable(),
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

/** Payload of the `version.created` event. */
export const VersionCreatedEventSchema = z.object({
  product_id: z.string(),
  version: ProductVersionSchema,
});
