/**
 * Assets (SPEC 4.1 `asset`): characters, scenes, props, on-screen text and voices found in the
 * script. Each has one product (reference image / text image / voice) whose versions carry the
 * candidates; locking an asset adopts and locks that product.
 */
import { z } from "zod";

import { MessageSchema } from "@/api/schemas/common";

export const AssetKindSchema = z.enum([
  "character",
  "scene",
  "prop",
  "text",
  "voice",
  "style",
  "world",
]);
export type AssetKind = z.infer<typeof AssetKindSchema>;

/** 已锁定 / 待选 (candidates exist) / 待生成 (none yet); derived from the product. */
export const AssetStatusSchema = z.enum(["locked", "choosing", "not_generated"]);
export type AssetStatus = z.infer<typeof AssetStatusSchema>;

export const TextMethodSchema = z.enum(["composite", "model"]);
export const TextStyleSchema = z.enum(["handwritten", "printed", "screen"]);
export const VoiceMethodSchema = z.enum(["design", "clone", "local"]);

export const AssetSchema = z.object({
  id: z.string(),
  series_id: z.string(),
  kind: AssetKindSchema,
  name: z.string(),
  /** Description = the intent layer of the asset's prompt. */
  intent: z.string(),
  /** Where the script mentions it: `components:asset.source.<code>` (剧本 场 1 △1 …). */
  source: MessageSchema,
  /** Shots of the current episode that use it. */
  shots: z.array(z.string()),
  product_id: z.string(),
  status: AssetStatusSchema,
  /** Candidate picked in the current version (0-based); the reference once locked. */
  pick: z.number().int().nonnegative(),
  /** On-screen text: the exact characters, how they are made, and the lettering. */
  text: z
    .object({ exact: z.string(), method: TextMethodSchema, style: TextStyleSchema })
    .nullable(),
  /** Voices: how the voice is made, and script lines to audition it with. */
  voice: z
    .object({
      method: VoiceMethodSchema,
      lines: z.array(z.object({ text: z.string(), tone: z.string() })),
    })
    .nullable(),
});
export type Asset = z.infer<typeof AssetSchema>;

/** `PATCH /assets/{id}` */
export const AssetPatchSchema = z.object({
  intent: z.string().optional(),
  pick: z.number().int().nonnegative().optional(),
  text: AssetSchema.shape.text.unwrap().partial().optional(),
  voice: z.object({ method: VoiceMethodSchema }).optional(),
});
export type AssetPatch = z.infer<typeof AssetPatchSchema>;

/** A version's candidates (`product_version.payload.candidates`). Labels are content. */
export const CandidatesPayloadSchema = z.object({
  candidates: z.array(
    z.object({
      /** OCR of an on-screen-text candidate. */
      ocr: z.string().nullable().optional(),
      /** Voice candidates: a short description and a static waveform (0–1). */
      label: z.string().nullable().optional(),
      waveform: z.array(z.number()).nullable().optional(),
    }),
  ),
});
export type CandidatesPayload = z.infer<typeof CandidatesPayloadSchema>;

/** `POST /episodes/{id}/assets/analyze` */
export const AnalyzeResultSchema = z.object({ added: z.number().int(), changed: z.number().int() });
