import { http, passthrough } from "msw";

import type { Episode, EpisodeProgress, StepId } from "@/api/schemas/episodes";
import { backendJson } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { adoptedTakeCount } from "@/mocks/handlers/generate";
import { confirmedShotCount } from "@/mocks/handlers/shots";
import { demoJson, v1 } from "@/mocks/http";

const BLANK = { state: "not_started", done: null, total: null, stale: 0 } as const;

export const seriesHandlers = [
  // The plan, the scripts and their gate are the backend's (分集规划, 剧本化); the demo series
  // lays its shots over them. Other series go to the backend untouched (plan「和 MSW 共存」).
  http.get(v1("/series/:id/episodes"), async ({ params, request }) => {
    const id = String(params.id);
    if (!getDb().series[id]) return passthrough();
    const real = await backendJson<Episode[] | null>(request.clone(), null);
    if (!real) return passthrough(); // backend down: let the page show the error
    return demoJson(
      real.map((e) => {
        const o = getDb().episodes.find((x) => x.id === e.id);
        return o ? { ...e, shot_count: o.shot_count } : e;
      }),
    );
  }),

  // The backend's badges (小说, 剧本, 素材 and their gates) with the demo's steps after 素材.
  http.get(v1("/episodes/:id/progress"), async ({ params, request }) => {
    const id = String(params.id);
    if (!getDb().episodes.some((e) => e.id === id)) return passthrough();
    const real = await backendJson<EpisodeProgress | null>(request.clone(), null);
    const steps: Record<StepId, EpisodeProgress["steps"][StepId]> = {
      novel: BLANK,
      script: BLANK,
      assets: BLANK,
      storyboard: BLANK,
      generate: BLANK,
      post: BLANK,
      ...real?.steps,
    };
    const demo = getDb().progress[id];
    if (demo) {
      const { storyboard, generate, post } = structuredClone(demo.steps);
      Object.assign(steps, { storyboard, generate, post });
      // 分镜 3/9 is the number of confirmed shots.
      if (steps.storyboard.state !== "not_started")
        Object.assign(steps.storyboard, confirmedShotCount(id));
      // 生成 3/9 is the number of shots with an adopted take.
      if (steps.generate.state !== "not_started")
        Object.assign(steps.generate, adoptedTakeCount(id));
    }
    return demoJson({ episode_id: id, steps });
  }),
];
