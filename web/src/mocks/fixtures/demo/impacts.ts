/**
 * Impact previews (prototype Spec 改画幅, Script 改已确认的段落). Keyed `<kind>:<target_id>`;
 * the script page (step 7) adds one per line. Names inside params are content, shown as is.
 */
import type { Impact } from "@/api/schemas/impact";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

type Preview = Omit<Impact, "id" | "change">;

export const impactPreviews: Record<string, Preview> = {
  // 成片规格 9:16 → any other aspect: $1.26 + $2.76 = $4.02.
  [`spec_aspect:${DEMO_SERIES_ID}`]: {
    lines: [
      { code: "keyframes_redraw", params: { count: 9, shots: 9 }, cost_usd: 1.26, optional: false },
      { code: "videos_redo", params: { count: 10, adopted: 3 }, cost_usd: 2.76, optional: false },
      {
        code: "ref_images_suggest",
        params: { count: 3, aspect: "9:16" },
        cost_usd: null,
        optional: true,
      },
    ],
    unaffected: { code: "unaffected_spec", params: {} },
    rerun_cost_usd: 4.02,
    stale: { storyboard: 9, generate: 10 },
  },
  // 剧本第 1 段（楼道）: prototype Script.dc.html b1.
  "line_edit:demo-l1": {
    lines: [
      { code: "asset_scene", params: { name: "老小区楼道 · 夜" }, cost_usd: null, optional: false },
      {
        code: "shots_range",
        params: { from: "1-01", to: "1-05", count: 5 },
        cost_usd: null,
        optional: false,
      },
      { code: "keyframes", params: { count: 5 }, cost_usd: null, optional: false },
      {
        code: "videos_adopted_candidates",
        params: { from: "1-01", to: "1-03", shot: "1-04", candidates: 4 },
        cost_usd: null,
        optional: false,
      },
    ],
    unaffected: null,
    rerun_cost_usd: 2.2,
    stale: { assets: 1, storyboard: 5, generate: 5 },
  },
};
