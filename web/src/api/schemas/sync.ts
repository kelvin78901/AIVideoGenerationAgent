/**
 * Sync to ComfyUI, a folder, Eagle and DaVinci Resolve (SPEC 14; 9.1 `GET/PUT /sync/targets`,
 * `POST /sync/run`, `GET /sync/log`, plus `GET /sync/board`). The studio is the only source of
 * truth: every target is a one-way push, except that ComfyUI can save new candidates back.
 */
import { z } from "zod";

import { MessageSchema, Timestamp } from "@/api/schemas/common";

export const SyncTargetIdSchema = z.enum(["comfy", "folder", "eagle", "resolve"]);
export type SyncTargetId = z.infer<typeof SyncTargetIdSchema>;

export const SyncTargetSchema = z.object({
  id: SyncTargetIdSchema,
  enabled: z.boolean(),
  /** ComfyUI is two-way (save back from its node); the others only receive. */
  direction: z.enum(["two_way", "one_way"]),
  /** Detection: `ok` reachable, `warn` usable with limits, `missing` not found. */
  state: z.enum(["ok", "warn", "missing"]),
  /** What detection found (`sync:status.<code>`). */
  status: MessageSchema,
  /** Resolve only: `fcpxml` (folder + timeline file) or `api` (Studio scripting). */
  mode: z.enum(["fcpxml", "api"]).nullable(),
  /** Modes that cannot be used here, with the reason (`sync:status.<code>`). */
  unavailable_modes: z.partialRecord(z.enum(["fcpxml", "api"]), MessageSchema),
});
export type SyncTarget = z.infer<typeof SyncTargetSchema>;

export const SYNC_KINDS = [
  "character",
  "scene",
  "prop",
  "text",
  "voice",
  "keyframe",
  "video_adopted",
  "video_all",
  "dub",
] as const;
export const SyncKindSchema = z.enum(SYNC_KINDS);
export type SyncKind = z.infer<typeof SyncKindSchema>;

export const SYNC_EXTRAS = ["prompt", "model_cost", "qa"] as const;
export const SyncExtraSchema = z.enum(SYNC_EXTRAS);

export const SyncRulesSchema = z.object({
  /** SPEC 14.1 triggers: on adopt / lock (default), on every new version, or manual only. */
  when: z.enum(["adopt", "every", "manual"]),
  kinds: z.array(SyncKindSchema),
  /** Folder layout: episode → scene → shot, or by asset type. */
  org: z.enum(["shot", "type"]),
  /** Metadata written next to each file (ComfyUI note, Eagle annotation, folder .json). */
  extras: z.array(SyncExtraSchema),
});
export type SyncRules = z.infer<typeof SyncRulesSchema>;

/** `GET /sync/targets` (and the answer of `PUT`). */
export const SyncSettingsSchema = z.object({
  targets: z.array(SyncTargetSchema),
  rules: SyncRulesSchema,
  /** Where one file lands under the current layout, computed by the backend's layout code. */
  preview: z.object({ dir: z.string(), files: z.array(z.string()) }),
});
export type SyncSettings = z.infer<typeof SyncSettingsSchema>;

export const SyncSettingsPatchSchema = z.object({
  targets: z
    .array(
      z.object({
        id: SyncTargetIdSchema,
        enabled: z.boolean().optional(),
        mode: z.enum(["fcpxml", "api"]).optional(),
      }),
    )
    .optional(),
  rules: SyncRulesSchema.partial().optional(),
});
export type SyncSettingsPatch = z.infer<typeof SyncSettingsPatchSchema>;

/** `GET /sync/log`: what was pushed where (`sync:log.<code>`, `sync:to.<code>`). */
export const SyncLogEntrySchema = z.object({
  id: z.string(),
  at: Timestamp,
  what: MessageSchema,
  to: z.array(MessageSchema),
});
export type SyncLogEntry = z.infer<typeof SyncLogEntrySchema>;

/** `POST /sync/run` and the `sync.updated` event. */
export const SyncRunSchema = z.object({
  run_id: z.string(),
  state: z.enum(["running", "done", "failed"]),
  done: z.number().int(),
  total: z.number().int(),
});
export type SyncRun = z.infer<typeof SyncRunSchema>;

// ---- ComfyUI board (SPEC 14.2): the episode's workflow as ComfyUI will lay it out ----

export const PortTypeSchema = z.enum(["image", "audio", "prompt", "size", "video"]);
export type PortType = z.infer<typeof PortTypeSchema>;

const Box = { x: z.number(), y: z.number(), w: z.number(), h: z.number() };

export const BoardGroupSchema = z.object({
  id: z.string(),
  /** `sync:board.group.<code>` (角色与音色, 场 N · …, 你的工作流 …). */
  title: MessageSchema,
  /** Group colour as ComfyUI stores it. */
  color: z.string(),
  ...Box,
});

export const BoardNodeSchema = z.object({
  id: z.string(),
  kind: z.enum(["image", "video", "audio", "note", "func"]),
  /** Node title as written into the workflow (asset or shot names: content). */
  title: z.string(),
  /** Caption under a thumbnail (`sync:board.caption.<code>`) and its tone. */
  caption: MessageSchema.nullable(),
  tone: z.enum(["ok", "pending", "running", "waiting"]).nullable(),
  /** Thumbnail placeholder: one of the demo gradients, or dashed when nothing exists yet. */
  thumb: z.object({ shade: z.number().int(), dashed: z.boolean(), small: z.boolean() }).nullable(),
  /** Note text (content). */
  text: z.string().nullable(),
  /** Function nodes: widgets and ports, top to bottom (ComfyUI labels; content). */
  rows: z.array(
    z.object({
      label: z.string(),
      dir: z.enum(["in", "out", "widget"]),
      type: PortTypeSchema.nullable(),
    }),
  ),
  /** Shown when the node is picked: `sync:board.fact.<key>` → value (content). */
  facts: z.array(z.object({ key: z.string(), value: z.string() })),
  ...Box,
});
export type BoardNode = z.infer<typeof BoardNodeSchema>;

export const BoardWireSchema = z.object({
  from: z.object({ node: z.string(), row: z.number().int() }),
  to: z.object({ node: z.string(), row: z.number().int() }),
  type: PortTypeSchema,
});
export type BoardWire = z.infer<typeof BoardWireSchema>;

/** `GET /sync/board?episode=` */
export const SyncBoardSchema = z.object({
  episode_id: z.string(),
  width: z.number(),
  height: z.number(),
  /** Opens the board in ComfyUI. */
  comfy_url: z.string(),
  groups: z.array(BoardGroupSchema),
  nodes: z.array(BoardNodeSchema),
  wires: z.array(BoardWireSchema),
});
export type SyncBoard = z.infer<typeof SyncBoardSchema>;
