/**
 * First run: machine scan and install (SPEC 12, 9.1 `POST /setup/scan`, `GET /setup/profile`,
 * `POST /setup/install`, `POST /setup/items/{id}/retry|skip`). Progress arrives as
 * `setup.progress` / `setup.log` events.
 */
import { z } from "zod";

import { MessageSchema, Timestamp } from "@/api/schemas/common";

export const MachineSchema = z.object({
  os: z.enum(["windows", "macos", "linux"]),
  /** null on machines without a usable GPU (Apple silicon counts as `mps`). */
  gpu: z
    .object({ name: z.string(), vram_gb: z.number(), backend: z.enum(["cuda", "mps"]) })
    .nullable(),
});
export type Machine = z.infer<typeof MachineSchema>;

/** Manifest groups (setup-manifest.yaml `group`): system, runtime, ComfyUI, weights, services. */
export const SetupGroupSchema = z.enum(["sys", "rt", "comfy", "w", "svc"]);
export type SetupGroup = z.infer<typeof SetupGroupSchema>;

/** What the scan found; `checking` until the item's detector has answered. */
export const DetectStatusSchema = z.enum([
  "checking",
  "ok",
  "missing",
  "old",
  "optional",
  "warn",
  "skip",
]);
export type DetectStatus = z.infer<typeof DetectStatusSchema>;

export const InstallStateSchema = z.enum(["queued", "running", "done", "failed", "skipped"]);
export type InstallState = z.infer<typeof InstallStateSchema>;

export const MirrorSchema = z.enum(["auto", "official", "cn"]);
export type Mirror = z.infer<typeof MirrorSchema>;

/** Manifest names are written in both languages (SPEC 12.1 `name: {zh, en}`). */
export const LocalizedSchema = z.object({ zh: z.string(), en: z.string() });
export type Localized = z.infer<typeof LocalizedSchema>;

export const SetupItemSchema = z.object({
  id: z.string(),
  group: SetupGroupSchema,
  name: LocalizedSchema,
  status: DetectStatusSchema,
  /** What the detector saw (`setup:found.<code>`); null while checking. */
  found: MessageSchema.nullable(),
  /** What to do about it (`setup:fix.<code>`); null when nothing is needed. */
  fix: MessageSchema.nullable(),
  /** Ticked by default; a failed required item blocks the steps that need it. */
  required: z.boolean(),
  installable: z.boolean(),
  /** null until the item is queued for install. */
  install: z
    .object({
      state: InstallStateSchema,
      pct: z.number(),
      /** Why it failed (`setup:error.<code>`). */
      error: MessageSchema.nullable(),
    })
    .nullable(),
});
export type SetupItem = z.infer<typeof SetupItemSchema>;

export const SetupPhaseSchema = z.enum(["idle", "scanning", "scanned", "installing", "done"]);
export type SetupPhase = z.infer<typeof SetupPhaseSchema>;

export const MachineProfileSchema = z.object({
  /** When the last full scan finished; null before the first one. */
  scanned_at: Timestamp.nullable(),
  machine: MachineSchema,
  phase: SetupPhaseSchema,
  /** Empty before the first scan; every manifest item for this platform afterwards. */
  items: z.array(SetupItemSchema),
  /** The last install request; null before the first install. */
  install: z
    .object({ mirror: MirrorSchema, dir: z.string(), items: z.array(z.string()) })
    .nullable(),
  /** Where models go unless the user picks another folder. */
  default_dir: z.string(),
  /** Preset suggested for this hardware (SPEC 12.2); null before the first scan. */
  recommendation: z
    .object({ preset: z.string(), reason: z.enum(["local_video", "no_cuda"]) })
    .nullable(),
});
export type MachineProfile = z.infer<typeof MachineProfileSchema>;

export const InstallRequestSchema = z.object({
  items: z.array(z.string()),
  mirror: MirrorSchema,
  dir: z.string(),
});
export type InstallRequest = z.infer<typeof InstallRequestSchema>;

/** `setup.progress`: the phase now, and the item that just changed. */
export const SetupProgressSchema = z.object({
  phase: SetupPhaseSchema,
  item: SetupItemSchema.nullable(),
});
export type SetupProgress = z.infer<typeof SetupProgressSchema>;

/** `setup.log`: one line of the install log (`setup:log.<code>`; `params.item` is an item id). */
export const SetupLogSchema = MessageSchema.extend({
  level: z.enum(["info", "ok", "warn"]),
});
export type SetupLog = z.infer<typeof SetupLogSchema>;
