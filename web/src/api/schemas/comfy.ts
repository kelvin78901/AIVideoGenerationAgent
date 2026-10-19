/**
 * The user's own ComfyUI (SPEC 6.4.1, 9.1): `GET /comfy/env` (what the last scan identified,
 * read-only), `GET / POST /comfy/snapshots` and `POST /comfy/snapshots/{id}/restore`.
 */
import { z } from "zod";

import { MessageSchema, Timestamp } from "@/api/schemas/common";

export const NodePackSchema = z.object({
  /** Folder (or module file) under custom_nodes. */
  name: z.string(),
  /** git: a clone; registry: installed by ComfyUI-Manager; manual: copied in by hand. */
  source: z.enum(["git", "registry", "manual", "unknown"]),
  version: z.string().nullable(),
  commit: z.string().nullable(),
  remote: z.string().nullable(),
  /** Node classes it provides (from `/object_info` while ComfyUI runs). */
  classes: z.array(z.string()),
});
export type NodePack = z.infer<typeof NodePackSchema>;

export const ComfyScanSchema = z.object({
  root: z.string().nullable(),
  kind: z.enum(["desktop", "portable", "folder", "server"]),
  /** Set while a server answers. */
  url: z.string().nullable(),
  port: z.number().nullable(),
  python_path: z.string().nullable(),
  manager: z
    .object({
      source: z.enum(["pip", "custom_node"]),
      version: z.string().nullable(),
      enabled: z.boolean().nullable(),
    })
    .nullable(),
  model_dirs: z.array(z.object({ folder: z.string(), path: z.string() })),
  models: z.array(
    z.object({
      folder: z.string(),
      name: z.string(),
      path: z.string().nullable(),
      size_bytes: z.number().nullable(),
    }),
  ),
  /** More model files than the scan lists. */
  models_truncated: z.boolean(),
  env_hash: z.string(),
});
export type ComfyScan = z.infer<typeof ComfyScanSchema>;

export const ComfyEnvSchema = z.object({
  comfyui_version: z.string().nullable(),
  comfyui_commit: z.string().nullable(),
  /** Python version ComfyUI runs on. */
  python: z.string().nullable(),
  torch: z.string().nullable(),
  node_packs: z.array(NodePackSchema),
  hash: z.string(),
  captured_at: Timestamp,
});
export type ComfyEnv = z.infer<typeof ComfyEnvSchema>;

/** `GET /comfy/env`: both null when the last scan found no ComfyUI (or before the first). */
export const ComfyViewSchema = z.object({
  scanned_at: Timestamp.nullable(),
  simulated: z.boolean(),
  comfy: ComfyScanSchema.nullable(),
  env: ComfyEnvSchema.nullable(),
});
export type ComfyView = z.infer<typeof ComfyViewSchema>;

export const ComfySnapshotSchema = z.object({
  id: z.string(),
  /** The name ComfyUI-Manager saved it under. */
  manager_name: z.string(),
  env_hash: z.string().nullable(),
  /** install: taken before an install changed ComfyUI; manual: 「现在存一份」. */
  reason: z.enum(["install", "manual"]),
  /** What that install was about to change (`setup:confirmReason.comfy_change`). */
  changes: z.array(MessageSchema),
  created_at: Timestamp,
  /** Set once a rollback to it was requested; it takes effect when ComfyUI restarts. */
  restored_at: Timestamp.nullable(),
});
export type ComfySnapshot = z.infer<typeof ComfySnapshotSchema>;

/** `POST /comfy/snapshots/{id}/restore`: we never restart the user's ComfyUI ourselves. */
export const RestoredSchema = z.object({
  snapshot: ComfySnapshotSchema,
  restart_required: z.boolean(),
});
export type Restored = z.infer<typeof RestoredSchema>;
