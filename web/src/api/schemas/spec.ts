/** Output spec (SPEC 4.1 `output_spec`, 13; `GET/PUT /series/{id}/spec`). */
import { z } from "zod";

import { Timestamp } from "@/api/schemas/common";

export const AspectSchema = z.enum(["9:16", "16:9", "3:4", "1:1", "21:9"]);
export type Aspect = z.infer<typeof AspectSchema>;

const Dims = z.object({ w: z.number().int(), h: z.number().int() });

export const OutputSpecSchema = z.object({
  series_id: z.string(),
  platform: z.enum(["cn", "intl", "wide", "custom"]),
  aspect: AspectSchema,
  delivery: z.enum(["1080p", "2k"]),
  fps: z.union([z.literal(24), z.literal(25), z.literal(30)]),
  episode_len: z.enum(["short", "mid", "long", "xl"]),
  subtitles: z.enum(["burn", "srt", "both"]),
  audio: z.object({ sample_rate: z.number(), lufs: z.number(), peak_dbtp: z.number() }),
  codec: z.string(),
  ai_mark: z.boolean(),
  /** Second version at export time: the other aspect, or null. */
  derive: AspectSchema.nullable(),
  locked_at: Timestamp.nullable(),
  /** Computed by the backend (`spec/dims.py`, the only place that derives sizes). */
  dims: z.object({ delivery: Dims, draft: Dims }),
});
export type OutputSpec = z.infer<typeof OutputSpecSchema>;

export const PlatformSchema = OutputSpecSchema.shape.platform;
export type Platform = z.infer<typeof PlatformSchema>;
export const DeliverySchema = OutputSpecSchema.shape.delivery;
export type Delivery = z.infer<typeof DeliverySchema>;

/** `PUT /series/{id}/spec`: changing the aspect of a locked spec goes through `/impact/*`. */
export const SpecPatchSchema = OutputSpecSchema.pick({
  platform: true,
  aspect: true,
  delivery: true,
  fps: true,
  episode_len: true,
  subtitles: true,
  derive: true,
}).partial();
export type SpecPatch = z.infer<typeof SpecPatchSchema>;

/**
 * `GET /spec/presets` (SPEC 13.1): platform presets and the sizes `spec/dims.py` gives every
 * aspect, so the page can show them before saving.
 */
export const SpecPresetsSchema = z.object({
  platforms: z.array(
    z.object({
      id: PlatformSchema,
      /** null = custom: keeps whatever aspect and size are chosen. */
      aspect: AspectSchema.nullable(),
      delivery: DeliverySchema.nullable(),
    }),
  ),
  dims: z.record(AspectSchema, z.object({ "1080p": Dims, "2k": Dims, draft: Dims })),
});
export type SpecPresets = z.infer<typeof SpecPresetsSchema>;

/** SPEC 13.3 `spec/compat.py`: can each model on the current route make this spec? */
export const CompatStatusSchema = z.enum(["native", "convert", "unsupported"]);
export type CompatStatus = z.infer<typeof CompatStatusSchema>;

export const CompatRowSchema = z.object({
  /** `spec:compat.stage.<code>`: keyframe, text_keyframe, sketch, video_draft … */
  stage: z.string(),
  model_keys: z.array(z.string()),
  status: CompatStatusSchema,
  /** How it is handled: `spec:compat.how.<code>`. */
  how: z.object({
    code: z.string(),
    params: z.record(z.string(), z.union([z.string(), z.number()])),
  }),
});
export type CompatRow = z.infer<typeof CompatRowSchema>;

/** `GET /series/{id}/spec/compat?aspect=` */
export const CompatSchema = z.object({ aspect: AspectSchema, rows: z.array(CompatRowSchema) });
export type Compat = z.infer<typeof CompatSchema>;
