/**
 * Novel, enrichment suggestions and the story bible (SPEC 4.1 `novel_source`, `suggestion`,
 * `bible_entity`). Text fields are the user's content and are shown as is.
 */
import { z } from "zod";

import { Timestamp } from "@/api/schemas/common";

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

export const NovelChapterSchema = z.object({
  /** null in an import preview (`dry_run`). */
  id: z.string().nullable(),
  /** 0-based. */
  idx: z.number().int().nonnegative(),
  /** The heading line; null for text before the first heading or a part of a length split. */
  title: z.string().nullable(),
  start: z.number().int(),
  end: z.number().int(),
  /** Number of the first paragraph, counted across the book. */
  para_start: z.number().int().nonnegative(),
  para_count: z.number().int().nonnegative(),
  chars: z.number().int().nonnegative(),
});
export type NovelChapter = z.infer<typeof NovelChapterSchema>;

export const NovelEncodingSchema = z.enum(["utf-8", "utf-16", "gb18030", "docx"]);
export const NovelSplitSchema = z.enum(["heading", "length"]);

export const NovelSourceSchema = z.object({
  id: z.string(),
  filename: z.string(),
  sha256: z.string(),
  encoding: NovelEncodingSchema,
  split_by: NovelSplitSchema,
  /** Paragraph characters (headings and blank lines excluded). */
  chars: z.number().int().nonnegative(),
  rights_confirmed_at: Timestamp,
  imported_at: Timestamp,
});
export type NovelSource = z.infer<typeof NovelSourceSchema>;

/** `GET /series/{id}/novel?chapter=`: the source in use and one chapter's paragraphs. */
export const NovelSchema = z.object({
  series_id: z.string(),
  /** null until a novel is imported (the page shows its empty state). */
  source: NovelSourceSchema.nullable(),
  chapters: z.array(NovelChapterSchema),
  /** idx of the chapter whose paragraphs are listed. */
  chapter: z.number().int().nonnegative().nullable(),
  paragraphs: z.array(NovelParagraphSchema),
});
export type Novel = z.infer<typeof NovelSchema>;

/** `POST /series/{id}/novel` (multipart `file`, `rights_confirmed`, `dry_run`). */
export const NovelImportSchema = z.object({
  /** Only what was found (the dialog's preview); nothing stored. */
  dry_run: z.boolean(),
  /** Same text as the current source: nothing was added. */
  unchanged: z.boolean(),
  source_id: z.string().nullable(),
  filename: z.string(),
  encoding: NovelEncodingSchema,
  split_by: NovelSplitSchema,
  chars: z.number().int().nonnegative(),
  chapters: z.array(NovelChapterSchema),
});
export type NovelImport = z.infer<typeof NovelImportSchema>;

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

/**
 * `GET /series/{id}/suggestions`: the 小说补全 version on screen (the product's current one) with
 * the user's decisions; deciding never makes a version.
 */
export const SuggestionsSchema = z.object({
  series_id: z.string(),
  /** null before the series has a novel. */
  product_id: z.string().nullable(),
  version_id: z.string().nullable(),
  /** false while the version on screen is not the adopted one (「未采纳」). */
  adopted: z.boolean(),
  source_id: z.string().nullable(),
  suggestions: z.array(SuggestionSchema),
});
export type Suggestions = z.infer<typeof SuggestionsSchema>;

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
  /** Paragraphs (numbered across the book, 0-based) that mention it. */
  paras: z.array(z.number().int().nonnegative()),
  source_spans: z.array(SourceSpanSchema),
  /** The user marked it as not to be changed by extraction (a rerun keeps it as it is). */
  frozen: z.boolean(),
});
export type BibleEntity = z.infer<typeof BibleEntitySchema>;

/** 「可能是同一个」: two entries the model judged to be the same, waiting for the user. */
export const MergeSuggestionSchema = z.object({
  id: z.string(),
  kind: BibleKindSchema,
  ids: z.array(z.string()),
  /** Model output, shown as is. */
  reason: z.string(),
});
export type MergeSuggestion = z.infer<typeof MergeSuggestionSchema>;

/** `GET /series/{id}/bible`: the 设定提取 version on screen (the product's current one). */
export const BibleSchema = z.object({
  series_id: z.string(),
  /** null before the series has a novel. */
  product_id: z.string().nullable(),
  version_id: z.string().nullable(),
  /** false while the version on screen is not the adopted one (「未采纳」). */
  adopted: z.boolean(),
  /** The source the spans point into (an older import after the novel was replaced). */
  source_id: z.string().nullable(),
  entities: z.array(BibleEntitySchema),
  merge_suggestions: z.array(MergeSuggestionSchema),
});
export type Bible = z.infer<typeof BibleSchema>;

/** `PATCH /bible/{id}`: only the fields sent change; a new name keeps the old one as an alias. */
export interface BiblePatch {
  name?: string;
  aliases?: string[];
  data?: Record<string, unknown>;
  frozen?: boolean;
}

/** `POST /bible/merge`: 确认合并 (the first id stays) / 不是同一个 / 拆分 (an alias). */
export type BibleMergeRequest =
  | { action: "merge" | "distinct"; ids: string[] }
  | { action: "split"; ids: [string]; alias: string };
