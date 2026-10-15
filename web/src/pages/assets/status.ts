import type { AssetStatus } from "@/api/schemas/assets";
import type { Tone } from "@/lib/tone";

export const STATUS_TONE: Record<AssetStatus, Tone> = {
  locked: "info",
  choosing: "warn",
  not_generated: "neutral",
};
