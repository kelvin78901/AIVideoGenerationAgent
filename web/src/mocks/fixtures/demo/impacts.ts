/**
 * Impact previews (prototype Spec 改画幅) and the demo episode's downstream of its script blocks
 * (prototype Script 改已确认的段落: shots, keyframes, videos), laid over the backend's preview.
 * Keyed `<kind>:<target_id>`. Names inside params are content, shown as is.
 */
import type { Impact } from "@/api/schemas/impact";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

type Preview = Omit<Impact, "id" | "change">;
type Line = Preview["lines"][number];

const line = (code: string, params: Line["params"] = {}): Line => ({
  code,
  params,
  cost_usd: null,
  optional: false,
});

/**
 * Editing a confirmed script block (prototype Script.dc.html `imp`): what goes stale after the
 * script and the rerun estimate (M4 makes shots real). Scene headings are `scene_edit`, the rest
 * `line_edit`.
 */
function scriptImpacts(): Record<string, Preview> {
  const p = (lines: Line[], cost: number, stale: Preview["stale"]): Preview => ({
    lines,
    unaffected: null,
    rerun_cost_usd: cost,
    stale,
  });
  const kf = (count: number) => line("keyframes", { count });
  return {
    "scene_edit:demo-b1": p(
      [
        line("asset_scene", { name: "老小区楼道 · 夜" }),
        line("shots_range", { from: "1-01", to: "1-05", count: 5 }),
        kf(5),
        line("videos_adopted_candidates", {
          from: "1-01",
          to: "1-03",
          shot: "1-04",
          candidates: 4,
        }),
      ],
      2.2,
      { assets: 1, storyboard: 5, generate: 5 },
    ),
    "line_edit:demo-b2": p(
      [
        line("asset_character_look", { name: "林晚" }),
        line("shot", { id: "1-01" }),
        kf(1),
        line("video_adopted", { id: "1-01" }),
      ],
      0.6,
      { assets: 1, storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b3": p(
      [
        line("asset_props", { names: "红色长柄伞、黄色便利贴" }),
        line("shot", { id: "1-02" }),
        kf(1),
        line("video_adopted", { id: "1-02" }),
      ],
      0.66,
      { assets: 2, storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b4": p(
      [
        line("asset_text", { name: "便利贴手写" }),
        line("shot", { id: "1-03" }),
        kf(1),
        line("video_adopted", { id: "1-03" }),
      ],
      0.38,
      { assets: 1, storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b5": p(
      [
        line("asset_voice_sample", { name: "林晚" }),
        line("shot_dialogue", { id: "1-04" }),
        line("video_candidates_redo", { id: "1-04", count: 4 }),
      ],
      0.33,
      { assets: 1, storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b6": p(
      [
        line("asset_props", { names: "旧发圈" }),
        line("shot", { id: "1-05" }),
        kf(1),
        line("video_not_generated", { id: "1-05" }),
      ],
      0.52,
      { assets: 1, storyboard: 1, generate: 1 },
    ),
    "scene_edit:demo-b7": p(
      [
        line("asset_scene", { name: "林晚出租屋 · 夜" }),
        line("shots_range", { from: "1-06", to: "1-09", count: 4 }),
        kf(4),
        line("videos_not_generated", { from: "1-06", to: "1-09" }),
      ],
      2.06,
      { assets: 1, storyboard: 4, generate: 4 },
    ),
    "line_edit:demo-b8": p(
      [line("shot", { id: "1-06" }), kf(1), line("video_not_generated", { id: "1-06" })],
      0.54,
      { storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b9": p(
      [
        line("asset_text", { name: "手机锁屏时间" }),
        line("shot", { id: "1-07" }),
        kf(1),
        line("video_not_generated", { id: "1-07" }),
      ],
      0.3,
      { assets: 1, storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b10": p(
      [
        line("shot_vo", { id: "1-06" }),
        line("dub_lines", { count: 1 }),
        line("video_audio_swap", { id: "1-06" }),
      ],
      0.01,
      { storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b11": p(
      [line("shot", { id: "1-08" }), kf(1), line("video_not_generated", { id: "1-08" })],
      0.62,
      { storyboard: 1, generate: 1 },
    ),
    "line_edit:demo-b12": p(
      [line("shot", { id: "1-09" }), kf(1), line("video_not_generated", { id: "1-09" })],
      0.46,
      { storyboard: 1, generate: 1 },
    ),
  };
}

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
};

/** Laid over the backend's preview of a demo script block (`mocks/handlers/impact.ts`). */
export const scriptDownstream: Record<string, Preview> = scriptImpacts();
