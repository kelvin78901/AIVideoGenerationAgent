/**
 * Post (prototype Post.dc.html; SPEC 9.1 additions): the episode timeline built from the
 * shots and their adopted takes, the audio and subtitle tracks, export checks and export.
 */
import { z } from "zod";

import { MessageSchema } from "@/api/schemas/common";

export const TransitionSchema = z.enum(["cut", "dissolve", "dip_black"]);
export type Transition = z.infer<typeof TransitionSchema>;

/** One shot on the picture track; its place follows the shot durations. */
export const ClipSchema = z.object({
  id: z.string(),
  shot_id: z.string(),
  shot_label: z.string(),
  start_s: z.number(),
  end_s: z.number(),
  /** The adopted take; null = not adopted yet, the keyframe stands in (and export marks it). */
  version_id: z.string().nullable(),
  /** SPEC 5.1: cut the first 0.3 s of H3 takes (a flash at the start). */
  trim_head: z.boolean(),
  /** How this clip comes in from the previous one. */
  transition: TransitionSchema,
  /** 0–100 */
  dialogue_volume: z.number().int().min(0).max(100),
  ambience_volume: z.number().int().min(0).max(100),
});
export type Clip = z.infer<typeof ClipSchema>;

/** `PATCH /clips/{id}` */
export const ClipPatchSchema = ClipSchema.pick({
  trim_head: true,
  transition: true,
  dialogue_volume: true,
  ambience_volume: true,
}).partial();
export type ClipPatch = z.infer<typeof ClipPatchSchema>;

/**
 * Audio on the dialogue / ambience+sfx / music tracks. `label` is content (林晚：……周屿？,
 * 雨声); `source=native` means the video model's own audio.
 */
export const AudioSegmentSchema = z.object({
  id: z.string(),
  track: z.enum(["dialogue", "ambience", "music"]),
  start_s: z.number(),
  end_s: z.number(),
  label: z.string(),
  source: z.enum(["native", "dub", "sfx", "music"]),
  /** The shot it belongs to (dialogue); null for spans across shots. */
  shot_id: z.string().nullable(),
  /** Component that makes it, for the Inspector (sfx, music); null for native audio. */
  component_id: z.string().nullable(),
});
export type AudioSegment = z.infer<typeof AudioSegmentSchema>;

/** Subtitle text comes from the script; ASR only aligns it in time. */
export const SubtitleSchema = z.object({
  id: z.string(),
  start_s: z.number(),
  end_s: z.number(),
  text: z.string(),
  /** The script line it was taken from. */
  line_id: z.string().nullable(),
  /** Edited here, no longer the script's words. */
  edited: z.boolean(),
});
export type Subtitle = z.infer<typeof SubtitleSchema>;

/** `PATCH /subtitles/{id}` */
export const SubtitlePatchSchema = z.object({ text: z.string() });
export type SubtitlePatch = z.infer<typeof SubtitlePatchSchema>;

/** `GET /episodes/{id}/timeline` */
export const TimelineSchema = z.object({
  episode_id: z.string(),
  duration_s: z.number(),
  clips: z.array(ClipSchema),
  audio: z.array(AudioSegmentSchema),
  subtitles: z.array(SubtitleSchema),
});
export type Timeline = z.infer<typeof TimelineSchema>;

/** One line of 导出检查: `message` → `post:check.<code>`. */
export const ExportCheckSchema = z.object({
  status: z.enum(["pass", "warn", "fail"]),
  message: MessageSchema,
});
export type ExportCheck = z.infer<typeof ExportCheckSchema>;

/** `GET /episodes/{id}/export/checks` */
export const ExportChecksSchema = z.object({ checks: z.array(ExportCheckSchema) });

export const ExportFormatSchema = z.enum(["mp4", "fcpxml", "otio", "srt"]);
export type ExportFormat = z.infer<typeof ExportFormatSchema>;

/** `POST /episodes/{id}/export` → Job */
export const ExportRequestSchema = z.object({ format: ExportFormatSchema });
