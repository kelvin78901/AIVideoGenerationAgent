/**
 * Episodes 1–3 of 《雨停之前》 as the MSW demo still knows them. The plan, the scripts, the
 * assets, the shots and the takes are the backend's (`studio/demo.py`); MSW only answers for 后期
 * (M7) of episode 1, the demo.
 */
import type { StepProgress } from "@/api/schemas/episodes";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

export const EP1 = "demo-e1";

/** The demo series' episodes: which ids the demo answers for. */
export interface DemoEpisode {
  id: string;
  series_id: string;
  idx: number;
}

export const episodes: DemoEpisode[] = [
  { id: EP1, series_id: DEMO_SERIES_ID, idx: 1 },
  { id: "demo-e2", series_id: DEMO_SERIES_ID, idx: 2 },
  { id: "demo-e3", series_id: DEMO_SERIES_ID, idx: 3 },
];

/** The steps the demo still answers for, laid over the backend's badges. */
export type DemoSteps = { post: StepProgress };

/** Nav badge of episode 1's 后期: 未开始. */
export const progress: Record<string, DemoSteps> = {
  [EP1]: {
    post: { state: "not_started", done: null, total: null, stale: 0 },
  },
};
