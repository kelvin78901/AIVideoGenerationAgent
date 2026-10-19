/**
 * Episodes 1–3 of 《雨停之前》 as the MSW demo still knows them. The plan itself — titles, hooks,
 * cliffhangers, beats, budgets — is the backend's (分集规划, `studio/demo.py`); MSW only adds
 * what its own later-step data says, until those steps move to the backend: shots (M4), and
 * 剧本已确认 from the demo's script gate (M2 step 10). Episode 1 《红伞》 is the demo.
 */
import type { EpisodeProgress } from "@/api/schemas/episodes";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

export const EP1 = "demo-e1";

/** What the demo lays over the backend's episode (`handlers/series.ts`). */
export interface EpisodeOverlay {
  id: string;
  series_id: string;
  idx: number;
  shot_count: number | null;
}

export const episodes: EpisodeOverlay[] = [
  {
    id: EP1,
    series_id: DEMO_SERIES_ID,
    idx: 1,
    shot_count: 9,
  },
  {
    id: "demo-e2",
    series_id: DEMO_SERIES_ID,
    idx: 2,
    shot_count: null,
  },
  {
    id: "demo-e3",
    series_id: DEMO_SERIES_ID,
    idx: 3,
    shot_count: null,
  },
];

/** Nav badges: 已确认 · 已确认 · 7/13 · 3/9 · 3/9 · 未开始. */
export const progress: Record<string, EpisodeProgress> = {
  [EP1]: {
    episode_id: EP1,
    steps: {
      novel: { state: "confirmed", done: null, total: null, stale: 0 },
      script: { state: "confirmed", done: null, total: null, stale: 0 },
      assets: { state: "in_progress", done: 7, total: 13, stale: 0 },
      storyboard: { state: "in_progress", done: 3, total: 9, stale: 0 },
      generate: { state: "in_progress", done: 3, total: 9, stale: 0 },
      post: { state: "not_started", done: null, total: null, stale: 0 },
    },
  },
};
