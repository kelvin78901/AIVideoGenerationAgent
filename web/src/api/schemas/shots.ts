/**
 * Shots (SPEC 4.1 `shot`): how each shot is framed, timed, voiced and blocked, which locked
 * assets it references, and where its first frame comes from. Text fields are content.
 */
import { z } from "zod";

/** 连续动作 (first frame = an earlier shot's last frame) / 同场切镜 / 换场. */
export const ShotTypeSchema = z.enum(["continuous", "same_scene_cut", "scene_change"]);
export type ShotType = z.infer<typeof ShotTypeSchema>;

/** 远景 / 中景 / 近景 / 特写 */
export const FramingSchema = z.enum(["wide", "medium", "close", "closeup"]);
export type Framing = z.infer<typeof FramingSchema>;

/** 固定 / 缓推 / 跟拍 / 摇 */
export const CameraMoveSchema = z.enum(["static", "push", "follow", "pan"]);
export type CameraMove = z.infer<typeof CameraMoveSchema>;

/** SPEC audio_mode A / B / C: 原生同步 / 先配音再对口型 / 无人声. */
export const AudioModeSchema = z.enum(["native", "tts", "none"]);
export type AudioMode = z.infer<typeof AudioModeSchema>;

export const BlockingItemSchema = z.object({
  id: z.string(),
  kind: z.enum(["character", "camera", "prop", "landmark"]),
  /** Content (林晚, 家门 …); the camera's label comes from the framing. */
  label: z.string(),
  /** Top-down position, 0–1 from the left / top. */
  x: z.number().min(0).max(1),
  y: z.number().min(0).max(1),
});
export type BlockingItem = z.infer<typeof BlockingItemSchema>;

export const ShotSchema = z.object({
  id: z.string(),
  episode_id: z.string(),
  scene_id: z.string(),
  /** 「1-04」: episode-shot number shown everywhere. */
  label: z.string(),
  /** 「场 1 · 楼道」 */
  scene_label: z.string(),
  idx: z.number().int().positive(),
  /** One-line summary for cards and the preview strip. */
  summary: z.string(),
  /** Picture description = intent layer of the keyframe prompt. */
  intent: z.string(),
  shot_type: ShotTypeSchema,
  framing: FramingSchema,
  camera_move: CameraMoveSchema,
  duration_s: z.number().positive(),
  duration_source: z.enum(["audio", "manual"]),
  /** The script lines the shot films (SPEC 4.1 `line_ids`): 镜头 ↔ 剧本行. */
  line_ids: z.array(z.string()),
  /** 「林晚（低声，愣住）：……周屿？」; null = no dialogue. */
  dialogue: z.string().nullable(),
  /** Ambient sound and effects. */
  sound: z.string().nullable(),
  audio_mode: AudioModeSchema,
  asset_ids: z.array(z.string()),
  /** Continuous shots: the shot whose last frame starts this one (not always the previous). */
  tail_from: z.string().nullable(),
  tail_note: z.string().nullable(),
  blocking: z.array(BlockingItemSchema),
  keyframe_product_id: z.string().nullable(),
  /** Video takes (slot=video): each version is one take on the candidate wall. */
  video_product_id: z.string().nullable(),
  /** Picked keyframe candidate (0-based) in the current version. */
  keyframe_pick: z.number().int().nonnegative(),
  confirmed: z.boolean(),
});
export type Shot = z.infer<typeof ShotSchema>;

/** `PATCH /shots/{id}` */
export const ShotPatchSchema = ShotSchema.pick({
  shot_type: true,
  framing: true,
  camera_move: true,
  duration_s: true,
  intent: true,
  audio_mode: true,
  asset_ids: true,
  blocking: true,
  keyframe_pick: true,
  confirmed: true,
}).partial();
export type ShotPatch = z.infer<typeof ShotPatchSchema>;
