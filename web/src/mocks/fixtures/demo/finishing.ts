/**
 * Episode 1's finishing products the demo still answers for (M6): 2K 精修 v1 SeedVR2 11:20
 * (1-01 至 1-03), 口型修复 none yet, 自动质检 v1 Qwen3-VL 10:58. The takes themselves are the
 * backend's (M5, `studio/demo.py` `DEMO_TAKES`).
 */
import type { Product } from "@/api/schemas/products";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { demoAt, demoVersion } from "@/mocks/fixtures/demo/products";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

export const PRODUCT_UPSCALE = "demo-p-up-e1";
export const PRODUCT_LIPSYNC = "demo-p-lip-e1";
export const PRODUCT_QA = "demo-p-qa-e1";

function episodeProduct(
  id: string,
  slot: Product["slot"],
  componentId: string,
  first: { model: string; at: string } | null,
): Product {
  const v = first
    ? demoVersion(id, componentId, {
        n: 1,
        origin: "run",
        model: first.model,
        at: demoAt(first.at),
      })
    : undefined;
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: "episode",
    owner_id: EP1,
    slot,
    component_id: componentId,
    current_version_id: v?.id ?? null,
    adopted_version_id: v?.id ?? null,
    locked_hash: null,
    status: v ? "adopted" : "empty",
    versions: v ? [v] : [],
    prompt: null,
    estimate: null,
    running: null,
  };
}

export const finishingProducts: Product[] = [
  episodeProduct(PRODUCT_UPSCALE, "upscale", "up", { model: "comfy/seedvr2", at: "11:20" }),
  episodeProduct(PRODUCT_LIPSYNC, "lipsync", "lip", null),
  episodeProduct(PRODUCT_QA, "qa", "qa", { model: "local/qwen3-vl-32b", at: "10:58" }),
];
