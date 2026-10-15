/** Episodes 1–3 of 《雨停之前》 (prototype Script / Dashboard). Episode 1 《红伞》 is the demo. */
import type { Episode, EpisodeProgress } from "@/api/schemas/episodes";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

export const EP1 = "demo-e1";

export const episodes: Episode[] = [
  {
    id: EP1,
    series_id: DEMO_SERIES_ID,
    idx: 1,
    title: "红伞",
    hook: "门口那把红伞，和三年没见的字迹。",
    cliffhanger: "她拿起了那把伞",
    target_seconds: 34,
    budget_usd: 15,
    stage: "in_progress",
  },
  {
    id: "demo-e2",
    series_id: DEMO_SERIES_ID,
    idx: 2,
    title: "十二点",
    hook: "她赶到便利店，离十二点还有四分钟。",
    cliffhanger: "便利店里没有他",
    target_seconds: 70,
    budget_usd: 15,
    stage: "script_pending",
  },
  {
    id: "demo-e3",
    series_id: DEMO_SERIES_ID,
    idx: 3,
    title: "旧发圈",
    hook: null,
    cliffhanger: null,
    target_seconds: 80,
    budget_usd: 15,
    stage: "not_started",
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
