/**
 * The demo episode's downstream of its script blocks that is not the backend's yet (prototype
 * Script 改已确认的段落): the video takes (M5), laid over the backend's preview, which lists the
 * assets, shots and keyframes itself. Keyed `<kind>:<target_id>`.
 */
import type { Impact } from "@/api/schemas/impact";

type Preview = Pick<Impact, "lines" | "rerun_cost_usd" | "stale">;
type Line = Preview["lines"][number];

const line = (code: string, params: Line["params"] = {}): Line => ({
  code,
  params,
  cost_usd: null,
  optional: false,
});

/** Editing a confirmed script block (prototype Script.dc.html `imp`): the takes of the shots
 * that film it and their rerun estimate. Scene headings are `scene_edit`, the rest `line_edit`. */
function scriptImpacts(): Record<string, Preview> {
  const p = (lines: Line[], cost: number, generate: number): Preview => ({
    lines,
    rerun_cost_usd: cost,
    stale: { generate },
  });
  const notYet = (id: string) => p([line("video_not_generated", { id })], 0.5, 1);
  return {
    "scene_edit:demo-b1": p(
      [
        line("videos_adopted_candidates", {
          from: "1-01",
          to: "1-03",
          shot: "1-04",
          candidates: 4,
        }),
      ],
      1.6,
      5,
    ),
    "line_edit:demo-b2": p([line("video_adopted", { id: "1-01" })], 0.46, 1),
    "line_edit:demo-b3": p([line("video_adopted", { id: "1-02" })], 0.46, 1),
    "line_edit:demo-b4": p([line("video_adopted", { id: "1-03" })], 0.24, 1),
    "line_edit:demo-b5": p([line("video_candidates_redo", { id: "1-04", count: 4 })], 0.33, 1),
    "line_edit:demo-b6": notYet("1-05"),
    "scene_edit:demo-b7": p([line("videos_not_generated", { from: "1-06", to: "1-09" })], 1.8, 4),
    "line_edit:demo-b8": notYet("1-06"),
    "line_edit:demo-b9": notYet("1-07"),
    "line_edit:demo-b10": p([line("video_audio_swap", { id: "1-06" })], 0.01, 1),
    "line_edit:demo-b11": notYet("1-08"),
    "line_edit:demo-b12": notYet("1-09"),
  };
}

/** Laid over the backend's preview of a demo script block (`mocks/handlers/impact.ts`). */
export const scriptDownstream: Record<string, Preview> = scriptImpacts();
