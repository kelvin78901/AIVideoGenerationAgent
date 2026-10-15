/**
 * An episode's script (SPEC 4.1 `scene`, `script_line`): scene headings and lines in order,
 * each traced back to the novel through `source_spans`. Text is content, shown as is.
 */
import { z } from "zod";

import { SourceSpanSchema } from "@/api/schemas/novel";

export const SceneSchema = z.object({
  id: z.string(),
  episode_id: z.string(),
  /** 1-based scene number across the series (场 1, 场 2 …). */
  idx: z.number().int().positive(),
  /** Scene heading as written: number, day / night, interior / exterior, place. */
  heading: z.string(),
  location_id: z.string().nullable(),
  time_of_day: z.string().nullable(),
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
  source_spans: z.array(SourceSpanSchema),
  /** Not in the novel; added by the model to make it filmable (「AI 新增」). */
  ai_added: z.boolean(),
  /** The episode's closing beat (「本集卡点」). */
  cliffhanger: z.boolean(),
  edited: z.boolean(),
});
export type ScriptLine = z.infer<typeof ScriptLineSchema>;

/** `GET /episodes/{id}/script`; empty when the episode has no script yet. */
export const ScriptSchema = z.object({
  episode_id: z.string(),
  scenes: z.array(SceneSchema),
  lines: z.array(ScriptLineSchema),
});
export type Script = z.infer<typeof ScriptSchema>;

/** `POST /lines/{id}/rewrite` / `POST /scenes/{id}/rewrite`: a proposal, nothing is saved. */
export const RewriteProposalSchema = z.object({ text: z.string(), model_key: z.string() });
export type RewriteProposal = z.infer<typeof RewriteProposalSchema>;
