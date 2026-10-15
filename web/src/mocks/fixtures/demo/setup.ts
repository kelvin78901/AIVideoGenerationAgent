/** Scan result of Kelvin's PC (prototype Setup, "Windows + RTX 5090"). */
import type { MachineProfile } from "@/api/schemas/setup";

export const profile: MachineProfile = {
  scanned_at: "2026-10-14T09:12:00+08:00",
  machine: { os: "windows", gpu: { name: "RTX 5090", vram_gb: 32, backend: "cuda" } },
};
