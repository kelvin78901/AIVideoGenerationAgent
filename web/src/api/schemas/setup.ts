/**
 * First run: machine scan and install (SPEC 12, 9.1 `POST /setup/scan`, `GET /setup/profile`,
 * `POST /setup/install`, `POST /setup/install/confirm|cancel`, `POST /setup/items/{id}/retry|skip`,
 * Mock's `POST /dev/setup/machine`). Progress arrives as `setup.progress` / `setup.log` events.
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
  /**
   * Installing it changes the user's own ComfyUI (SPEC 6.4.1): never ticked by default, listed
   * for approval, and a ComfyUI-Manager snapshot is taken first.
   */
  touches_comfy: z.boolean(),
  /** What it downloads (bytes, the manifest's `size_gb`); null when it downloads nothing. */
  size_bytes: z.number().nullable(),
  /** Rough seconds of its steps that are not downloads (a clone, a pip install …). */
  work_s: z.number(),
  /** null until the item is queued for install. */
  install: z
    .object({
      state: InstallStateSchema,
      /** One decimal; an item with downloads goes by bytes and stays at 99 until it is done. */
      pct: z.number(),
      /** Why it failed (`setup:error.<code>`). */
      error: MessageSchema.nullable(),
      /** Downloads while it runs: bytes over all its files (the sizes known so far). */
      bytes_done: z.number().nullable(),
      bytes_total: z.number().nullable(),
      /** Bytes per second over the last few seconds; null in the first second and while checking. */
      speed: z.number().nullable(),
      /** Seconds left at that speed. */
      eta_s: z.number().nullable(),
      /** A finished file's sha256 is being checked (tens of seconds for a big one). */
      verifying: z.boolean(),
    })
    .nullable(),
});
export type SetupItem = z.infer<typeof SetupItemSchema>;
export type ItemInstall = NonNullable<SetupItem["install"]>;

export const SetupPhaseSchema = z.enum(["idle", "scanning", "scanned", "installing", "done"]);
export type SetupPhase = z.infer<typeof SetupPhaseSchema>;

export const InstallInfoSchema = z.object({
  mirror: MirrorSchema,
  dir: z.string(),
  items: z.array(z.string()),
  /**
   * What the user has to approve before anything starts (SPEC 12.2-5, 6.4.1): changes to their
   * ComfyUI (`setup:confirmReason.comfy_change`), elevation (`admin`), downloads over 10 GB
   * (`large_download`). Empty once approved; the install waits while it is not.
   */
  confirm: z.array(MessageSchema),
  /** The `comfy_change` lines, kept after approval: what the snapshot was taken for. */
  changes: z.array(MessageSchema),
  /** The ComfyUI-Manager snapshot taken before the first change (`/comfy/snapshots` id). */
  snapshot: z.string().nullable(),
  /** Why no snapshot could be taken (`setup:error.snapshot_<reason>`); ComfyUI was left alone. */
  snapshot_error: MessageSchema.nullable(),
});
export type InstallInfo = z.infer<typeof InstallInfoSchema>;

export const MachineProfileSchema = z.object({
  /** When the last full scan finished; null before the first one. */
  scanned_at: Timestamp.nullable(),
  machine: MachineSchema,
  phase: SetupPhaseSchema,
  /** Empty before the first scan; every manifest item for this platform afterwards. */
  items: z.array(SetupItemSchema),
  /** The last install request (items in install order); null before the first install. */
  install: InstallInfoSchema.nullable(),
  /** Where models go unless the user picks another folder. */
  default_dir: z.string(),
  /** Preset suggested for this hardware (SPEC 12.2); null before the first scan. */
  recommendation: z
    .object({ preset: z.string(), reason: z.enum(["local_video", "no_cuda"]) })
    .nullable(),
  /** Mock's sample machines (no real scan): the page shows the 示例机器 switch. */
  simulated: z.boolean(),
  /**
   * This machine's download speed (bytes/s): the last install's, else a short download during
   * the scan; null when never measured. Times the downloads in the estimates.
   */
  download_bps: z.number().nullable(),
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
