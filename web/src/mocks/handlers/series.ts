import { http } from "msw";

import { getDb } from "@/mocks/db";
import { demoError, demoJson, v1 } from "@/mocks/http";

export const seriesHandlers = [
  http.get(v1("/series/:id"), ({ params }) => {
    const series = getDb().series[String(params.id)];
    return series ? demoJson(series) : demoError(404, "series_not_found", { id: params.id });
  }),

  http.get(v1("/series/:id/episodes"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().series[id]) return demoError(404, "series_not_found", { id });
    return demoJson(getDb().episodes.filter((e) => e.series_id === id));
  }),

  http.get(v1("/series/:id/spec"), ({ params }) => {
    const spec = getDb().specs[String(params.id)];
    return spec ? demoJson(spec) : demoError(404, "series_not_found", { id: params.id });
  }),

  http.get(v1("/episodes/:id/progress"), ({ params }) => {
    const id = String(params.id);
    const progress = getDb().progress[id];
    if (progress) return demoJson(progress);
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
