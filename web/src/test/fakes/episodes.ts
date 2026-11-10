/**
 * Fake 分集规划 for page tests: the demo series' adopted plan and step badges as the Mock backend
 * answers them (`test/data/episodes.json`, written by tests/api/test_web_fixtures.py). Edits
 * follow the backend's rules (`episodes/ops.py`): a dragged beat goes to `position` among the
 * target episode's other beats (the end when omitted) and everything is renumbered; the budget
 * is a plain setting.
 */
import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  BeatPatchSchema,
  EpisodePatchSchema,
  EpisodeProgressSchema,
  EpisodeSchema,
  STEP_IDS,
  type BeatPatch,
  type Episode,
  type EpisodePatch,
  type StepProgress,
} from "@/api/schemas/episodes";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import { fakeAssetsBadge } from "@/test/fakes/assets";
import { fakeGenerateBadge } from "@/test/fakes/generate";
import { fakeShotsBadge } from "@/test/fakes/shots";
import data from "@/test/data/episodes.json";

const demo = z.array(EpisodeSchema).parse(data.episodes);
const demoProgress = z.record(z.string(), EpisodeProgressSchema).parse(data.progress);

/** State of the fake; `resetFakeEpisodes()` (called by `backend()`) restores it. */
export const fakeEpisodes = {
  list: structuredClone(demo),
  progress: structuredClone(demoProgress),
  /** The novel gate of the other series (no episodes; the demo's shows on its episodes). */
  seriesNovel: {} as Record<string, StepProgress["state"]>,
  /** Every edit sent, in order. */
  episodePatches: [] as ({ id: string } & EpisodePatch)[],
  beatPatches: [] as ({ id: string } & BeatPatch)[],
  /** Set to answer every edit with this error (e.g. 409 `product_locked`). */
  failWith: null as { status: number; code: string } | null,
};

export function resetFakeEpisodes() {
  fakeEpisodes.list = structuredClone(demo);
  fakeEpisodes.progress = structuredClone(demoProgress);
  fakeEpisodes.seriesNovel = {};
  fakeEpisodes.episodePatches = [];
  fakeEpisodes.beatPatches = [];
  fakeEpisodes.failWith = null;
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

function renumber(list: Episode[]) {
  for (const e of list)
    e.beats.forEach((b, i) => Object.assign(b, { idx: i + 1, episode_id: e.id }));
}

/** `ops.patch_beat`: the error code, or null once applied. */
function patchBeat(list: Episode[], id: string, body: BeatPatch): string | null {
  const source = list.find((e) => e.beats.some((b) => b.id === id));
  const beat = source?.beats.find((b) => b.id === id);
  if (!source || !beat) return "beat_not_found";
  if (body.text !== undefined) {
    if (!body.text.trim()) return "beat_empty";
    beat.text = body.text.trim();
  }
  if (body.emotion !== undefined) beat.emotion = Math.round(body.emotion * 100) / 100;
  if (body.episode_id !== undefined || body.position !== undefined) {
    const target = body.episode_id ? list.find((e) => e.id === body.episode_id) : source;
    if (!target) return "episode_not_found";
    source.beats = source.beats.filter((b) => b.id !== id);
    const at = Math.min(body.position ?? target.beats.length, target.beats.length);
    target.beats.splice(at, 0, beat);
  }
  renumber(list);
  return null;
}

/** The fake backend's answer to what the MSW demo merges in (`mocks/backend.ts`), or null. */
export function episodesBackendFetch(url: URL): Response | null {
  const m = /\/episodes\/([^/]+)\/progress$/.exec(url.pathname);
  const id = decodeURIComponent(m?.[1] ?? "");
  const progress = m ? fakeEpisodes.progress[id] : undefined;
  if (!progress) return null;
  // 素材, 分镜 and 生成 count the fake assets, shots and takes as they are now (a test moves them).
  const steps = { ...progress.steps };
  steps.assets = fakeAssetsBadge(id) ?? steps.assets;
  steps.storyboard = fakeShotsBadge(id) ?? steps.storyboard;
  steps.generate = fakeGenerateBadge(id) ?? steps.generate;
  return HttpResponse.json({ ...progress, steps });
}

/** `known`: the series the fake backend has. Other series have no plan yet. */
export function episodeHandlers(known: (id: string) => boolean) {
  return [
    http.get("*/api/v1/series/:id/episodes", ({ params }) => {
      const id = String(params.id);
      if (id === DEMO_SERIES_ID) return HttpResponse.json(fakeEpisodes.list);
      return known(id) ? HttpResponse.json([]) : error(404, "series_not_found", { id });
    }),

    // `GET /series/{id}/progress`: 小说 only (the demo's as its episodes show it).
    http.get("*/api/v1/series/:id/progress", ({ params }) => {
      const id = String(params.id);
      if (id !== DEMO_SERIES_ID && !known(id)) return error(404, "series_not_found", { id });
      const blank: StepProgress = { state: "not_started", done: null, total: null, stale: 0 };
      const steps = Object.fromEntries(STEP_IDS.map((s) => [s, blank]));
      const demoNovel = Object.values(fakeEpisodes.progress)[0]?.steps.novel;
      steps.novel =
        id === DEMO_SERIES_ID && demoNovel
          ? demoNovel
          : { ...blank, state: fakeEpisodes.seriesNovel[id] ?? "in_progress" };
      return HttpResponse.json({ series_id: id, steps });
    }),

    http.patch("*/api/v1/episodes/:id", async ({ params, request }) => {
      const id = String(params.id);
      const ep = fakeEpisodes.list.find((e) => e.id === id);
      if (!ep) return error(404, "episode_not_found", { id });
      const body = EpisodePatchSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      fakeEpisodes.episodePatches.push({ id, ...body.data });
      const { budget_usd, ...plan } = body.data;
      if (budget_usd !== undefined) ep.budget_usd = budget_usd;
      if (Object.keys(plan).length && fakeEpisodes.failWith)
        return error(fakeEpisodes.failWith.status, fakeEpisodes.failWith.code);
      if (plan.title !== undefined && !plan.title.trim()) return error(422, "title_required");
      if (plan.title !== undefined) ep.title = plan.title.trim();
      if (plan.hook !== undefined) ep.hook = plan.hook.trim() || null;
      if (plan.cliffhanger !== undefined) ep.cliffhanger = plan.cliffhanger.trim() || null;
      if (plan.target_seconds !== undefined) ep.target_seconds = plan.target_seconds;
      return HttpResponse.json(ep);
    }),

    http.patch("*/api/v1/beats/:id", async ({ params, request }) => {
      const id = String(params.id);
      const body = BeatPatchSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      fakeEpisodes.beatPatches.push({ id, ...body.data });
      if (fakeEpisodes.failWith)
        return error(fakeEpisodes.failWith.status, fakeEpisodes.failWith.code);
      const next = structuredClone(fakeEpisodes.list);
      const code = patchBeat(next, id, body.data);
      if (code) return error(code.endsWith("_not_found") ? 404 : 422, code, { id });
      fakeEpisodes.list = next;
      return HttpResponse.json(next);
    }),
  ];
}
