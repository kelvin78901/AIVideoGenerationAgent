import type { Aspect, Platform, SafeArea, SafeAreaKind, SpecPresets } from "@/api/schemas/spec";

/** Width and height of each aspect. */
export const ASPECT_RATIO: Record<Aspect, [number, number]> = {
  "9:16": [9, 16],
  "16:9": [16, 9],
  "3:4": [3, 4],
  "1:1": [1, 1],
  "21:9": [21, 9],
};

/**
 * Whose UI covers the picture (prototype Spec.dc.html): a portrait spec for a short-drama app
 * (国内 / 海外, or custom) has its top bar, button column and caption block; another portrait
 * player and every landscape or square one only their controls.
 */
export function safeAreaKind(aspect: Aspect, platform: Platform): SafeAreaKind {
  const [w, h] = ASPECT_RATIO[aspect];
  if (h <= w) return "horizontal";
  const app = platform === "cn" || platform === "intl" || platform === "custom";
  return app ? "vertical_app" : "vertical_player";
}

/** The spec's safe area, as `GET /spec/presets` gives it (the spec page, the storyboard). */
export function safeAreaOf(presets: SpecPresets, aspect: Aspect, platform: Platform): SafeArea {
  return presets.safe_areas[safeAreaKind(aspect, platform)];
}
