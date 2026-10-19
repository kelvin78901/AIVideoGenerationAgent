import { http, passthrough } from "msw";

import type { Episode, EpisodeProgress, StepId } from "@/api/schemas/episodes";
import { backendJson } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { lockedAssetCount } from "@/mocks/handlers/assets";
import { adoptedTakeCount } from "@/mocks/handlers/generate";
import { confirmedShotCount } from "@/mocks/handlers/shots";
import { demoJson, v1 } from "@/mocks/http";

const BLANK = { state: "not_started", done: null, total: null, stale: 0 } as const;

export const seriesHandlers = [
  // The plan and the scripts are the backend's (分集规划, 剧本化); the demo series lays its
  // shots over them, and 剧本已确认 while the script gate is still the demo's (step 10). Other
  // series go to the backend untouched (plan「和 MSW 共存」).
  http.get(v1("/series/:id/episodes"), async ({ params, request }) => {
    const id = String(params.id);
    if (!getDb().series[id]) return passthrough();
    const real = await backendJson<Episode[] | null>(request.clone(), null);
    if (!real) return passthrough(); // backend down: let the page show the error
    return demoJson(
      real.map((e) => {
        const o = getDb().episodes.find((x) => x.id === e.id);
        if (!o) return e;
        const confirmed = getDb().progress[e.id]?.steps.script.state === "confirmed";
        return {
          ...e,
          shot_count: o.shot_count,
          script_status: confirmed && e.script_status !== "none" ? "confirmed" : e.script_status,
        };
      }),
    );
  }),

  // The backend's badges with the demo's: the gates are still MSW's (小说 is series-wide, so
  // episode 1's badge holds for every demo episode), and so are the steps after 剧本. 待更新
  // counts stay the backend's.
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
    const novel = getDb().progress[EP1]?.steps.novel;
    if (novel) steps.novel = { ...novel, stale: steps.novel.stale };
    const demo = getDb().progress[id];
    if (demo) {
      const { assets, storyboard, generate, post, script } = structuredClone(demo.steps);
      Object.assign(steps, { assets, storyboard, generate, post });
      // 剧本 is the backend's; 已确认 while the script gate is still the demo's (step 10).
      if (script.state === "confirmed" && steps.script.state !== "not_started")
        steps.script = { ...steps.script, state: "confirmed" };
      // 素材 7/13 is the number of locked assets.
      if (steps.assets.state !== "not_started") Object.assign(steps.assets, lockedAssetCount());
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
