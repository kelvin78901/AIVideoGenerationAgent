import { http, passthrough } from "msw";

import type { EpisodeProgress, StepId } from "@/api/schemas/episodes";
import { backendJson } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { demoJson, v1 } from "@/mocks/http";

const BLANK = { state: "not_started", done: null, total: null, stale: 0 } as const;

export const seriesHandlers = [
  // The backend's badges (小说 … 生成 and their gates) with the demo's 后期 of episode 1.
  // Other episodes go to the backend untouched (plan「和 MSW 共存」).
  http.get(v1("/episodes/:id/progress"), async ({ params, request }) => {
    const id = String(params.id);
    const demo = getDb().progress[id];
    if (!demo) return passthrough();
    const real = await backendJson<EpisodeProgress | null>(request.clone(), null);
    const steps: Record<StepId, EpisodeProgress["steps"][StepId]> = {
      novel: BLANK,
      script: BLANK,
      assets: BLANK,
      storyboard: BLANK,
      generate: BLANK,
      ...real?.steps,
      ...structuredClone(demo),
    };
    return demoJson({ episode_id: id, steps });
  }),
];
