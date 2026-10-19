/**
 * An episode's script (SPEC 4.1 `scene`, `script_line`): scene headings and lines in order,
 * each traced back to the novel through `paras` (and `source_spans`). Text is content, shown as
 * is.
 */
import { z } from "zod";

import { SourceSpanSchema } from "@/api/schemas/novel";

export const SceneSchema = z.object({
  id: z.string(),
  episode_id: z.string(),
  /** 1-based scene number across the series (场 1, 场 2 …), counted by the backend. */
  idx: z.number().int().positive(),
  /** Day / night, interior / exterior, place (夜、内、林晚出租屋), without the scene number. */
  heading: z.string(),
  location_id: z.string().nullable(),
  time_of_day: z.string().nullable(),
  /** Novel paragraphs (0-based, across the book) the scene comes from. */
  paras: z.array(z.number().int().nonnegative()),
  source_spans: z.array(SourceSpanSchema),
  /** Changed by hand after the script was generated (「已修改」). */
  edited: z.boolean(),
});
export type Scene = z.infer<typeof SceneSchema>;

export const LineTypeSchema = z.enum(["action", "dialogue", "vo", "sfx"]);
export type LineType = z.infer<typeof LineTypeSchema>;

export const ScriptLineSchema = z.object({
  id: z.string(),
  scene_id: z.string(),
  /** Order within the episode, scene headings included. */
  idx: z.number().int().nonnegative(),
  type: LineTypeSchema,
  character_id: z.string().nullable(),
  character_name: z.string().nullable(),
  /** Delivery in brackets: 「低声，愣住」, 「OS」. */
  tone: z.string().nullable(),
  text: z.string(),
  /** Emotion of an action beat (表格「情绪/语气」). */
  mood: z.string().nullable(),
  duration_s: z.number().nullable(),
  /** A voice-over laid over another shot instead of taking its own time (「叠在 1-06」). */
  overlay_shot: z.string().nullable(),
  /** Novel paragraphs (0-based) the line comes from, the paragraph of an addition included. */
  paras: z.array(z.number().int().nonnegative()),
  /** Paragraph spans; `sug:<id>` for an accepted addition (小说补全) the line uses. */
  source_spans: z.array(SourceSpanSchema),
  /** Not in the novel; added by the model to make it filmable (「AI 新增」). */
  ai_added: z.boolean(),
  /** The episode's closing beat (「本集卡点」). */
  cliffhanger: z.boolean(),
  edited: z.boolean(),
});
export type ScriptLine = z.infer<typeof ScriptLineSchema>;

/**
 * `GET /episodes/{id}/script`: the version on screen (the product's current one); empty when the
 * episode has no script yet.
 */
export const ScriptSchema = z.object({
  episode_id: z.string(),
  product_id: z.string().nullable(),
  version_id: z.string().nullable(),
  /** False while the version on screen is not the adopted one (「未采纳」). */
  adopted: z.boolean(),
  source_id: z.string().nullable(),
  scenes: z.array(SceneSchema),
  lines: z.array(ScriptLineSchema),
});
export type Script = z.infer<typeof ScriptSchema>;

/** `PATCH /lines/{id}` (`text`) / `PATCH /scenes/{id}` (`heading`): an unconfirmed script. */
export const BlockPatchSchema = z.union([
  z.object({ text: z.string().min(1) }),
  z.object({ heading: z.string().min(1) }),
]);
export type BlockPatch = z.infer<typeof BlockPatchSchema>;

/** Body of `POST /lines|scenes/{id}/rewrite`; `confirm_budget` after a 409 `over_budget`. */
export const BlockRewriteRequestSchema = z.object({
  model: z.string().optional(),
  instruction: z.string().optional(),
  confirm_budget: z.boolean().optional(),
});
export type BlockRewriteRequest = z.infer<typeof BlockRewriteRequestSchema>;

/** `POST /lines/{id}/rewrite` / `POST /scenes/{id}/rewrite`: a proposal, nothing is saved. */
export const RewriteProposalSchema = z.object({ text: z.string(), model_key: z.string() });
export type RewriteProposal = z.infer<typeof RewriteProposalSchema>;
