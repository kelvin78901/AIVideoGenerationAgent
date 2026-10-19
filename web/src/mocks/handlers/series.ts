import { http, passthrough } from "msw";

import { EpisodePatchSchema } from "@/api/schemas/episodes";
import { getDb } from "@/mocks/db";
import { lockedAssetCount } from "@/mocks/handlers/assets";
import { adoptedTakeCount } from "@/mocks/handlers/generate";
import { confirmedShotCount } from "@/mocks/handlers/shots";
import { demoError, demoJson, v1 } from "@/mocks/http";

export const seriesHandlers = [
  // Other series than the demo one go to the backend (plan「和 MSW 共存」).
  http.get(v1("/series/:id/episodes"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().series[id]) return passthrough();
    return demoJson(getDb().episodes.filter((e) => e.series_id === id));
  }),

  // Only the budget for now (Models page 本集 API 预算); SPEC 9.1 `PATCH /episodes/{id}`.
  http.patch(v1("/episodes/:id"), async ({ params, request }) => {
    const db = getDb();
    const ep = db.episodes.find((e) => e.id === String(params.id));
    if (!ep) return demoError(404, "episode_not_found", { id: params.id });
    const body = EpisodePatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    if (body.data.budget_usd !== undefined) {
      ep.budget_usd = body.data.budget_usd;
      // The demo summary is episode 1's; the top bar reads its budget.
      if (ep.idx === 1) db.summary.episode.budget_usd = body.data.budget_usd;
    }
    return demoJson(ep);
  }),

  http.get(v1("/episodes/:id/progress"), ({ params }) => {
    const id = String(params.id);
    const progress = getDb().progress[id];
    if (progress) {
      // 素材 7/13 is the number of locked assets.
      const assets = progress.steps.assets;
      if (assets.state !== "not_started") Object.assign(assets, lockedAssetCount());
      // 分镜 3/9 is the number of confirmed shots.
      const board = progress.steps.storyboard;
      if (board.state !== "not_started") Object.assign(board, confirmedShotCount(id));
      // 生成 3/9 is the number of shots with an adopted take.
      const gen = progress.steps.generate;
      if (gen.state !== "not_started") Object.assign(gen, adoptedTakeCount(id));
      return demoJson(progress);
    }
    if (!getDb().episodes.some((e) => e.id === id))
      return demoError(404, "episode_not_found", { id });
    // Episodes without work yet: every step not started.
    const blank = { state: "not_started", done: null, total: null, stale: 0 } as const;
    const steps = Object.fromEntries(
      ["novel", "script", "assets", "storyboard", "generate", "post"].map((s) => [s, blank]),
    );
    return demoJson({ episode_id: id, steps });
  }),
];
