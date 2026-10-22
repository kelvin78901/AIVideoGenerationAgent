import type { AssetStatus } from "@/api/schemas/assets";
import type { ProductVersion } from "@/api/schemas/products";
import type { Aspect } from "@/api/schemas/spec";
import type { Tone } from "@/lib/tone";

/** Width (px) of a candidate or view card: small and the same on any screen (a picture is
 * looked at in the lightbox). Portrait cards are narrower, so their height stays modest. */
export const CARD_WIDTH: Record<Aspect, number> = {
  "9:16": 148,
  "3:4": 168,
  "1:1": 180,
  "16:9": 252,
  "21:9": 300,
};

/** Where a card's picture sits: inside its 2 px border and 6 px padding (`p-1.5`). */
export const CARD_INSET = 8;

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
