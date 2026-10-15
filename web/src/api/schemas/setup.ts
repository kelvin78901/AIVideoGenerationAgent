/** First-run scan result (SPEC 12; `GET /setup/profile`). Extended by the Setup page. */
import { z } from "zod";

import { Timestamp } from "@/api/schemas/common";

export const MachineSchema = z.object({
  os: z.enum(["windows", "macos", "linux"]),
  /** null on machines without a usable GPU (Apple silicon counts as `mps`). */
  gpu: z
    .object({ name: z.string(), vram_gb: z.number(), backend: z.enum(["cuda", "mps"]) })
    .nullable(),
});
export type Machine = z.infer<typeof MachineSchema>;

export const MachineProfileSchema = z.object({
  scanned_at: Timestamp.nullable(),
  machine: MachineSchema,
});
export type MachineProfile = z.infer<typeof MachineProfileSchema>;
