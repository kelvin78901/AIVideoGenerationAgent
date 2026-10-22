/**
 * 台词配音 (M3, `assets/dub.py`): each spoken line of an episode in its speaker's locked voice,
 * and how long lines and scenes run once dubbed (`pipeline/timing.py`).
 */
import { z } from "zod";

import { VersionFileSchema } from "@/api/schemas/products";

/** The emotions a line can be read with (`config/voice.yaml`; `enums:emotion.<id>`). */
export const EMOTIONS = ["calm", "angry", "crying", "whisper", "shout"] as const;

/**
 * done: current audio; stale: the line or the voice changed since; missing: never dubbed;
 * running / failed: the take now or the last one; no_voice / voice_not_locked: the speaker's
 * voice is not there or not locked yet, so the line cannot be dubbed.
 */
export const DubStatusSchema = z.enum([
  "done",
  "stale",
  "missing",
  "running",
  "failed",
  "no_voice",
  "voice_not_locked",
]);
export type DubStatus = z.infer<typeof DubStatusSchema>;

export const DubLineSchema = z.object({
  line_id: z.string(),
  scene_id: z.string(),
  idx: z.number().int(),
  text: z.string(),
  tone: z.string(),
  /** The character's name as the script writes it. */
  speaker: z.string(),
  voice_asset_id: z.string().nullable(),
  voice_name: z.string().nullable(),
  /** The line's audio product; made on its first take. */
  product_id: z.string().nullable(),
  status: DubStatusSchema,
  emotion: z.string(),
  /** Chosen by hand; else from the tone's keywords. */
  emotion_set: z.boolean(),
  /** What the tone calls for (`config/voice.yaml` tones), chosen by hand or not. */
  tone_emotion: z.string(),
  /** The adopted take (`role: audio`, with its waveform). */
  audio: VersionFileSchema.nullable(),
  /** The audio's length; before it is dubbed, the script's estimate. */
  seconds: z.number(),
});
export type DubLine = z.infer<typeof DubLineSchema>;

export const DubSceneSchema = z.object({
  scene_id: z.string(),
  /** Series-wide 场号. */
  number: z.number().int(),
  /** Its spoken lines one after another. */
  seconds: z.number(),
  dubbed: z.number().int(),
  lines: z.number().int(),
});
export type DubScene = z.infer<typeof DubSceneSchema>;

/** `GET /episodes/{id}/dub` */
export const DubSchema = z.object({
  episode_id: z.string(),
  lines: z.array(DubLineSchema),
  scenes: z.array(DubSceneSchema),
  done: z.number().int(),
  total: z.number().int(),
});
export type Dub = z.infer<typeof DubSchema>;

/** `POST /episodes/{id}/dub`: `dry_run` only estimates; `line_ids` dubs those lines again. */
export interface DubRequest {
  dry_run?: boolean;
  line_ids?: string[];
}

export const DubSkipSchema = z.object({
  line_id: z.string(),
  code: z.enum(["no_voice", "voice_not_locked", "product_busy"]),
  /** The voice's (or speaker's) name. */
  name: z.string(),
});
export type DubSkip = z.infer<typeof DubSkipSchema>;

export const DubStartSchema = z.object({
  estimate_usd: z.number(),
  /** Lines to dub (or dubbed). */
  lines: z.number().int(),
  jobs: z.array(z.string()),
  skipped: z.array(DubSkipSchema),
});
export type DubStart = z.infer<typeof DubStartSchema>;
