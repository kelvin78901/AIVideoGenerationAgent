import type { Aspect } from "@/api/schemas/spec";

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
