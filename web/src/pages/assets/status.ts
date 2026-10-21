import type { AssetStatus } from "@/api/schemas/assets";
import type { ProductVersion } from "@/api/schemas/products";
import type { Tone } from "@/lib/tone";

export const STATUS_TONE: Record<AssetStatus, Tone> = {
  locked: "info",
  choosing: "warn",
  not_generated: "neutral",
};

/** A voice version still to finish: its auditions (candidates), not a final's anchor and
 * emotion variants. Only a final is locked. */
export function isVoiceDraft(version: ProductVersion | undefined): boolean {
  return !!version?.files.some((f) => f.role === "candidate");
}
