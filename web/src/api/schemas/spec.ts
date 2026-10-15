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
