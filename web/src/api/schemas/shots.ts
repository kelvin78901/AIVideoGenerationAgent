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

/** 镜头契约 (M5.5): 表演 / 动作 / 对白 / 插入（没有人：静物、空镜）. */
export const ContractKindSchema = z.enum(["performance", "action", "dialogue", "insert"]);
export type ContractKind = z.infer<typeof ContractKindSchema>;

/** How a spoken line is said: 对白（嘴动）/ 画外 / 内心独白（嘴闭着）. */
export const DeliverySchema = z.enum(["dialogue", "offscreen", "inner"]);
export type Delivery = z.infer<typeof DeliverySchema>;

/** A person or thing and its state (「家门」: 「关着」). Content. */
export const StateItemSchema = z.object({ subject: z.string(), state: z.string() });
export type StateItem = z.infer<typeof StateItemSchema>;

/** 镜头契约 (M5.5, backend `shots/contract.py`): the keyframe draws `start`; the video keeps
 * to `beats` actions (an insert: 0, only small motion) and never undoes a change; props are in
 * their `state`; `delivery` maps each spoken line id to how it is said. */
export const ShotContractSchema = z.object({
  kind: ContractKindSchema,
  beats: z.number().int().min(0).max(4),
  start: z.array(StateItemSchema),
  end: z.array(StateItemSchema),
  props: z.array(z.object({ asset_id: z.string(), state: z.string() })),
  delivery: z.record(z.string(), DeliverySchema),
  /** A continuous shot without a start of its own: it begins where the shot it follows ends. */
  start_inherited: z.boolean(),
});
export type ShotContract = z.infer<typeof ShotContractSchema>;

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
  /** Series-wide 场号. */
  scene_no: z.number().int().nonnegative(),
  /** Where the scene is: its heading without day / night and 内 / 外 (「林晚出租屋」). */
  scene_place: z.string(),
  idx: z.number().int().positive(),
  /** One-line summary for cards and the preview strip. */
  summary: z.string(),
  /** Picture description = intent layer of the keyframe prompt. */
  intent: z.string(),
  /** The plan gave a new picture description since the user edited this one. */
  seed_changed: z.boolean(),
  shot_type: ShotTypeSchema,
  framing: FramingSchema,
  camera_move: CameraMoveSchema,
  /** How long it runs (M4, Kelvin 2026-10-21): dialogue by its audio, the rest by the plan or
   * the user, never shorter than its spoken lines (`min_s`). */
  duration_s: z.number().positive(),
  duration_source: z.enum(["audio", "manual"]),
  /** Its spoken lines' audio with a breath each side; 0 when nobody speaks. */
  min_s: z.number().nonnegative(),
  planned_s: z.number().nullable(),
  manual_s: z.number().nullable(),
  /** The longest take the video route makes (H3: 15 s); null = no limit known. */
  longest_s: z.number().nullable(),
  /** Longer than that: split the shot. */
  split_hint: z.boolean(),
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
  /** That candidate's picture (`fileUrl`); null = no keyframe yet, or a continuous shot. */
  keyframe_sha256: z.string().nullable(),
  confirmed: z.boolean(),
  /** Confirmed, but the shot's settings or its keyframe changed since (「待更新」). */
  confirm_stale: z.boolean(),
  contract: ShotContractSchema,
});
export type Shot = z.infer<typeof ShotSchema>;

/** `PATCH /shots/{id}`; `duration_s: null` = back to automatic (its audio, or the plan's). */
export const ShotPatchSchema = ShotSchema.pick({
  shot_type: true,
  framing: true,
  camera_move: true,
  intent: true,
  audio_mode: true,
  asset_ids: true,
  blocking: true,
  keyframe_pick: true,
  confirmed: true,
})
  .extend({
    duration_s: z.number().positive().nullable(),
    /** Only the contract fields that change (`delivery`: only the lines that change). */
    contract: ShotContractSchema.omit({ start_inherited: true }).partial(),
  })
  .partial();
export type ShotPatch = z.infer<typeof ShotPatchSchema>;

/** The impact preview's `shot_edit`: settings, or a split (after a line) / a merge with the
 * next shot of a confirmed shot. */
export type ShotEdit = ShotPatch & { split?: { after_line_id: string | null }; merge?: boolean };
