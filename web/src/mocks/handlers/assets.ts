import { http, passthrough } from "msw";

import type { Asset } from "@/api/schemas/assets";
import type { Impact } from "@/api/schemas/impact";
import { backendJson } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { demoJson, v1 } from "@/mocks/http";

/**
 * Assets are the backend's since M3 step 3 (list, edits, candidates, lock, unlock). The demo
 * series only lays its shots over them: which shots of episode 1 use each asset (M4 makes shots
 * real), and what unlocking means for those shots in the impact preview.
 */
const demoShots = (assetId: string) => getDb().assets.find((a) => a.id === assetId)?.shots ?? [];

/** The backend's assets of the demo series, or null when it is down. */
export async function backendAssets(request: Request, seriesId: string): Promise<Asset[] | null> {
  const url = new URL(`/api/v1/series/${encodeURIComponent(seriesId)}/assets`, request.url);
  return backendJson<Asset[] | null>(new Request(url), null);
}

/** 素材 n/m: the locked ones among the series' assets (the backend's). */
export async function lockedAssetCount(
  request: Request,
  seriesId: string,
): Promise<{ done: number; total: number } | null> {
  const list = await backendAssets(request, seriesId);
  if (!list) return null;
  return { done: list.filter((a) => a.status === "locked").length, total: list.length };
}

/** Unlocking a demo asset: the shots that use it as a reference go stale (laid over the
 * backend's preview). */
export function assetUnlockOverlay(assetId: string): Omit<Impact, "id" | "change"> | undefined {
  const shots = demoShots(assetId);
  const n = shots.length;
  if (!n) return undefined;
  const cost = Math.round(n * 0.14 * 100) / 100;
  return {
    lines: [
      {
        code: "shot_refs",
        params: { ids: shots.join(" "), count: n },
        cost_usd: null,
        optional: false,
      },
      { code: "keyframes", params: { count: n }, cost_usd: cost, optional: false },
    ],
    unaffected: { code: "unlock_keeps_adopted", params: {} },
    rerun_cost_usd: cost,
    stale: { storyboard: n, generate: n },
  };
}

export const assetHandlers = [
  // The backend's list with the demo's shots on it; other series are the backend's alone.
  http.get(v1("/series/:id/assets"), async ({ params, request }) => {
    const id = String(params.id);
    if (!getDb().series[id]) return passthrough();
    const real = await backendJson<Asset[] | null>(request.clone(), null);
    if (!real) return passthrough(); // backend down: let the page show the error
    return demoJson(real.map((a) => ({ ...a, shots: demoShots(a.id) })));
  }),

  // 重新分析剧本: the demo script has not changed since the last analysis (the backend's
  // answer is a job; the page follows it in step 4).
  http.post(v1("/episodes/:id/assets/analyze"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().episodes.some((e) => e.id === id)) return passthrough();
    return demoJson({ added: 0, changed: 0 });
  }),
];
