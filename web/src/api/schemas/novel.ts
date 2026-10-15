/**
 * Novel, enrichment suggestions and the story bible (SPEC 4.1 `novel_source`, `suggestion`,
 * `bible_entity`). Text fields are the user's content and are shown as is.
 */
import { z } from "zod";

export const SourceSpanSchema = z.object({
  source_id: z.string(),
  start: z.number().int(),
  end: z.number().int(),
});
export type SourceSpan = z.infer<typeof SourceSpanSchema>;

export const NovelParagraphSchema = z.object({
  /** 0-based; the UI shows 01, 02 … */
  idx: z.number().int().nonnegative(),
  text: z.string(),
  start: z.number().int(),
  end: z.number().int(),
});
export type NovelParagraph = z.infer<typeof NovelParagraphSchema>;

/** `GET /series/{id}/novel` */
export const NovelSchema = z.object({
  series_id: z.string(),
  source: z.object({ id: z.string(), filename: z.string(), sha256: z.string() }),
  paragraphs: z.array(NovelParagraphSchema),
});
export type Novel = z.infer<typeof NovelSchema>;

/**
 * What a suggestion fills in. The first four are the enrich component's (prototype tags 外貌 /
 * 光线 / 心理外化 / 卡点); the rest are SPEC 4.1's consistency checks.
 */
export const SuggestionKindSchema = z.enum([
  "appearance",
  "lighting",
  "inner_to_action",
  "cliffhanger",
  "motive",
  "timeline",
  "consistency",
  "gap",
]);
export type SuggestionKind = z.infer<typeof SuggestionKindSchema>;

export const SuggestionStatusSchema = z.enum(["pending", "accepted", "rejected", "rewritten"]);
export type SuggestionStatus = z.infer<typeof SuggestionStatusSchema>;

export const SuggestionSchema = z.object({
  id: z.string(),
  series_id: z.string(),
  kind: SuggestionKindSchema,
  /** Paragraph the addition is appended to. */
  para_idx: z.number().int().nonnegative(),
  anchor_span: SourceSpanSchema,
  /** Why (model output, shown as is). */
  reason: z.string(),
  /** The text to insert. */
  text: z.string(),
  status: SuggestionStatusSchema,
  /** Set once rewritten on request (「已按要求重写」), kept after accepting. */
  rewrite_instruction: z.string().nullable(),
  rewritten_by: z.string().nullable(),
});
export type Suggestion = z.infer<typeof SuggestionSchema>;

export const BibleKindSchema = z.enum(["character", "location", "prop", "event", "relation"]);
export type BibleKind = z.infer<typeof BibleKindSchema>;

export const BibleEntitySchema = z.object({
  id: z.string(),
  series_id: z.string(),
  kind: BibleKindSchema,
  name: z.string(),
  aliases: z.array(z.string()),
  /** Kind-specific fields; `summary` is the one-line description the novel page shows. */
  data: z.looseObject({ summary: z.string().optional() }),
  source_spans: z.array(SourceSpanSchema),
  /** The user marked it as not to be changed by extraction. */
  frozen: z.boolean(),
});
export type BibleEntity = z.infer<typeof BibleEntitySchema>;
