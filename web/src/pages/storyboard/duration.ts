import type { Shot } from "@/api/schemas/shots";

/** Where a shot's length comes from: the user, its audio, or the plan. */
export function durationSource(s: Shot): "manual" | "audio" | "plan" {
  if (s.manual_s !== null) return "manual";
  return s.duration_source === "audio" ? "audio" : "plan";
}
