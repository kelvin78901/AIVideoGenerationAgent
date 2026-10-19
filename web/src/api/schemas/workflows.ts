/**
 * Workflow library (SPEC 6.4.2–6.4.6, 9.1 `/workflows/*`): every ComfyUI workflow is registered as
 * a local model (`comfy/<slug>`). M1 shows it with demo data (MSW); the backend comes in M5.
 */
import { z } from "zod";

import { MessageSchema, Timestamp } from "@/api/schemas/common";

/** recommended: ships with the studio, pinned and tested; mine: imported and passed a trial run. */
export const WorkflowTierSchema = z.enum(["recommended", "mine", "unverified"]);
export type WorkflowTier = z.infer<typeof WorkflowTierSchema>;

/** The inputs and outputs the studio fills in or reads back (SPEC 6.4.3). */
export const SlotSchema = z.enum([
  "first_frame",
  "video_in",
  "ref_image",
  "prompt",
  "negative",
  "dialogue_audio",
  "width",
  "height",
  "fps",
  "seconds",
  "seed",
  "video_out",
  "image_out",
  "audio_out",
]);
export type Slot = z.infer<typeof SlotSchema>;

export const BindingSchema = z.object({
  slot: SlotSchema,
  /** Reference images come numbered: 1, 2, 3 … */
  index: z.number().nullable(),
  /** Found by the node's title (`_meta.title`), never its id. */
  node_title: z.string(),
  node_class: z.string(),
  /** The input field; null for an output node. */
  field: z.string().nullable(),
  /** dramastudio: a DramaStudio input / output node, nothing to confirm; guessed: waits for a yes. */
  state: z.enum(["dramastudio", "confirmed", "guessed"]),
});
export type Binding = z.infer<typeof BindingSchema>;

/** A node in the workflow that a binding can point at (title + its fields). */
export const WorkflowNodeSchema = z.object({
  title: z.string(),
  class_type: z.string(),
  fields: z.array(z.string()),
});
export type WorkflowNode = z.infer<typeof WorkflowNodeSchema>;

export const MissingPackSchema = z.object({
  name: z.string(),
  /** Node classes the workflow uses that this pack provides. */
  classes: z.array(z.string()),
  source: z.enum(["registry", "git"]),
  version: z.string().nullable(),
  url: z.string().nullable(),
});
export type MissingPack = z.infer<typeof MissingPackSchema>;

export const MissingModelSchema = z.object({
  folder: z.string(),
  name: z.string(),
  size_bytes: z.number().nullable(),
  url: z.string().nullable(),
});
export type MissingModel = z.infer<typeof MissingModelSchema>;

/** The last health check (SPEC 6.4.4-1, 6.4.5): what is missing, what broke. */
export const WorkflowCheckSchema = z.object({
  at: Timestamp,
  status: z.enum(["ok", "missing", "broken"]),
  node_classes: z.object({ found: z.number(), total: z.number() }),
  missing_packs: z.array(MissingPackSchema),
  missing_models: z.array(MissingModelSchema),
  /** Other problems: a bound title gone, a field renamed (`workflows:problem.<code>`). */
  problems: z.array(MessageSchema),
});
export type WorkflowCheck = z.infer<typeof WorkflowCheckSchema>;

/** The last trial run on the sample inputs (SPEC 6.4.4-3). */
export const WorkflowTrialSchema = z.object({
  at: Timestamp,
  status: z.enum(["running", "passed", "failed"]),
  job_id: z.string().nullable(),
  /** Draft size and the shortest duration, read from the output spec. */
  w: z.number(),
  h: z.number(),
  seconds: z.number(),
  duration_s: z.number().nullable(),
  vram_gb: z.number().nullable(),
  /** Why it failed (`workflows:trialError.<code>`). */
  error: MessageSchema.nullable(),
});
export type WorkflowTrial = z.infer<typeof WorkflowTrialSchema>;

export const WorkflowSchema = z.object({
  id: z.string(),
  slug: z.string(),
  /** The local model it registers as. */
  model_key: z.string(),
  name: z.string(),
  tier: WorkflowTierSchema,
  /** repo: `workflows/<slug>/`; user: imported into `~/.drama-studio/workflows/<slug>/`. */
  source: z.enum(["repo", "user"]),
  /** Where it was imported from (a dropped file name or a ComfyUI workflow path). */
  origin: z.string().nullable(),
  /** Components it serves (`enums:component.<id>`). */
  components: z.array(z.string()),
  /** Same fields as providers.yaml `caps`. */
  caps: z.object({
    aspects: z.array(z.string()),
    max_seconds: z.number().nullable(),
    refs: z.number().nullable(),
    vram_gb: z.number().nullable(),
  }),
  file_sha256: z.string(),
  /** The file differs from the registered hash: demoted to unverified until a trial passes. */
  file_changed: z.boolean(),
  uses_dramastudio_nodes: z.boolean(),
  bindings: z.array(BindingSchema),
  nodes: z.array(WorkflowNodeSchema),
  check: WorkflowCheckSchema.nullable(),
  trial: WorkflowTrialSchema.nullable(),
  created_at: Timestamp,
  updated_at: Timestamp,
});
export type Workflow = z.infer<typeof WorkflowSchema>;

/** `GET /comfy/workflows`: what ComfyUI's own workflow list has (its user data folder). */
export const ComfyWorkflowFileSchema = z.object({
  path: z.string(),
  modified_at: Timestamp,
  /** Already in the library (that workflow's id), or the studio's own asset board. */
  imported_as: z.string().nullable(),
  board: z.boolean(),
});
export type ComfyWorkflowFile = z.infer<typeof ComfyWorkflowFileSchema>;

/** `POST /workflows/import`: a dropped JSON file, or a path from ComfyUI's list. */
export const ImportRequestSchema = z.union([
  z.object({ file_name: z.string(), workflow: z.record(z.string(), z.unknown()) }),
  z.object({ comfy_path: z.string() }),
]);
export type ImportRequest = z.infer<typeof ImportRequestSchema>;

/** `POST /workflows/{id}/deps`: the change list for the missing node packs and models. */
export const DepsPlanSchema = z.object({
  /** `setup:confirmReason.comfy_change` lines, as the install dialog shows them. */
  changes: z.array(MessageSchema),
});
export type DepsPlan = z.infer<typeof DepsPlanSchema>;
