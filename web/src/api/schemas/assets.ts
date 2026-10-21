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
/** On-screen text: the exact characters, how they are made, and the lettering. */
export const TextSettingsSchema = z.object({
  exact: z.string(),
  method: TextMethodSchema,
  style: TextStyleSchema,
});
export type TextSettings = z.infer<typeof TextSettingsSchema>;
/** Why OCR does not match: characters or punctuation left out, some read as others, or text
 * on a base meant for compositing. */
export const OcrIssueSchema = z.enum(["missing", "wrong", "has_text"]);
export const VoiceMethodSchema = z.enum(["design", "clone", "local"]);

/** A scene of the episode asked for that the asset appears in, and its lines there. */
export const AssetSceneSchema = z.object({
  scene_id: z.string(),
  episode_id: z.string(),
  /** Series-wide 场号, as the script page numbers scenes. */
  number: z.number().int(),
  /** The lines it is in (speaker, or named in an action line); empty = the whole scene. */
  line_ids: z.array(z.string()),
});
export type AssetScene = z.infer<typeof AssetSceneSchema>;

export const AssetSchema = z.object({
  id: z.string(),
  series_id: z.string(),
  kind: AssetKindSchema,
  name: z.string(),
  /** Description = the intent layer of the asset's prompt. */
  intent: z.string(),
  /** Where the script mentions it: `components:asset.source.<code>` (剧本 场 1 △1 …). */
  source: MessageSchema,
  /** Shots of the current episode that use it (M4; the demo's are laid over by MSW). */
  shots: z.array(z.string()),
  /** Scenes of the episode asked for (`?episode=`) it appears in. */
  scenes: z.array(AssetSceneSchema),
  product_id: z.string(),
  status: AssetStatusSchema,
  /** Candidate picked in the current version (0-based); the reference once locked. */
  pick: z.number().int().nonnegative(),
  text: TextSettingsSchema.nullable(),
  /** Voices: how the voice is made, and script lines to audition it with. */
  voice: z
    .object({
      method: VoiceMethodSchema,
      lines: z.array(z.object({ text: z.string(), tone: z.string() })),
    })
    .nullable(),
  /** What the analysis said about it (e.g. 「第 2 集出场」 for one not used yet). */
  note: z.string().nullable(),
  /** The script now describes it differently from what its candidates were made from. */
  seed_changed: z.boolean(),
});
export type Asset = z.infer<typeof AssetSchema>;

/** `PATCH /assets/{id}` */
export const AssetPatchSchema = z.object({
  intent: z.string().optional(),
  pick: z.number().int().nonnegative().optional(),
  text: TextSettingsSchema.partial().optional(),
  voice: z.object({ method: VoiceMethodSchema }).optional(),
});
export type AssetPatch = z.infer<typeof AssetPatchSchema>;

/** A version's candidates (`product_version.payload.candidates`). Labels are content. */
export const CandidatesPayloadSchema = z.object({
  candidates: z.array(
    z.object({
      /** On-screen text: what OCR read (null: not checked, no OCR on this machine)… */
      ocr: z.string().nullable().optional(),
      /** …whether it is what the text must say (a base for compositing: blank)… */
      ocr_ok: z.boolean().nullable().optional(),
      /** …and why not. */
      ocr_issue: OcrIssueSchema.nullable().optional(),
      /** Voice candidates: a short description and a static waveform (0–1). */
      label: z.string().nullable().optional(),
      waveform: z.array(z.number()).nullable().optional(),
    }),
  ),
  /** On-screen text: the settings the candidates were made with. */
  text: TextSettingsSchema.nullable().optional(),
});
export type CandidatesPayload = z.infer<typeof CandidatesPayloadSchema>;

/** `POST /assets/{id}/lock`: by default the picked candidate of the version on screen.
 * On-screen text OCR read differently is refused (409 `ocr_mismatch`) unless `force`. */
export const AssetLockSchema = z.object({
  version_id: z.string().optional(),
  idx: z.number().int().nonnegative().optional(),
  force: z.boolean().optional(),
});
export type AssetLock = z.infer<typeof AssetLockSchema>;

/** `GET /episodes/{id}/assets/matrix`: 出场矩阵, the episode's scenes × the assets it uses. */
export const AssetMatrixSchema = z.object({
  episode_id: z.string(),
  scenes: z.array(z.object({ id: z.string(), number: z.number().int(), heading: z.string() })),
  assets: z.array(z.object({ id: z.string(), kind: AssetKindSchema, name: z.string() })),
  /** One per (asset, scene) it appears in; `line_ids` empty = the whole scene. */
  cells: z.array(
    z.object({ asset_id: z.string(), scene_id: z.string(), line_ids: z.array(z.string()) }),
  ),
});
export type AssetMatrix = z.infer<typeof AssetMatrixSchema>;
