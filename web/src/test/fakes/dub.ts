/**
 * Fake 台词配音 for page tests: episode 1's spoken lines before and after 「全部配音」 as the Mock
 * backend answers them (`test/data/dub.json`, written by tests/api/test_web_fixtures.py),
 * following the backend's rules (`assets/dub.py`) as far as the pages need them:
 * - a line whose voice is not locked (`test/fakes/assets.ts`) waits for it and is skipped;
 * - 「全部配音」 estimates first (`dry_run`), then dubs every line without current audio; with
 *   `line_ids`, those lines again (a new take: its audio is the dubbed one in the export);
 * - a line's emotion by hand, or from its tone again (`null`).
 */
import { http, HttpResponse } from "msw";

import { injectEvent } from "@/api/events";
import {
  DubSchema,
  DubStartSchema,
  type Dub,
  type DubLine,
  type DubRequest,
  type DubSkip,
} from "@/api/schemas/dub";
import data from "@/test/data/dub.json";
import { fakeAssets } from "@/test/fakes/assets";

const before = DubSchema.parse(data.before);
const after = DubSchema.parse(data.after);
const estimate = DubStartSchema.parse(data.estimate);
const chars = (lines: DubLine[]) => lines.reduce((n, x) => n + x.text.length, 0);
// The Mock price per character, from the export's estimate.
const perChar = estimate.estimate_usd / chars(before.lines.filter((x) => x.status === "missing"));

/** State of the fake; `resetFakeDub()` (called by `backend()`) restores it. */
export const fakeDub = {
  dub: structuredClone(before),
  /** Takes made, line ids in order. */
  takes: [] as string[],
};

export function resetFakeDub() {
  fakeDub.dub = structuredClone(before);
  fakeDub.takes = [];
}

/** Every line dubbed, as after 「全部配音」. */
export function dubFakeEpisode() {
  fakeDub.dub = structuredClone(after);
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

/** Its voice is locked: the voice asset's product (`test/fakes/assets.ts`). */
function voiceLocked(x: DubLine): boolean {
  const asset = fakeAssets.assets.find((a) => a.id === x.voice_asset_id);
  const p = asset && fakeAssets.products.find((q) => q.id === asset.product_id);
  return !!p?.locked_hash;
}

/** The backend's `status`: the line's own state, and its voice's. */
function current(): Dub {
  const dub = fakeDub.dub;
  for (const x of dub.lines) {
    if (x.audio) continue;
    if (!x.voice_asset_id) x.status = "no_voice";
    else if (!voiceLocked(x)) x.status = "voice_not_locked";
    else if (x.status === "voice_not_locked" || x.status === "no_voice") x.status = "missing";
  }
  for (const s of dub.scenes) {
    const mine = dub.lines.filter((x) => x.scene_id === s.scene_id);
    s.seconds = Math.round(mine.reduce((n, x) => n + x.seconds, 0) * 1000) / 1000;
    s.dubbed = mine.filter((x) => x.audio).length;
    s.lines = mine.length;
  }
  dub.done = dub.lines.filter((x) => x.status === "done").length;
  dub.total = dub.lines.length;
  return dub;
}

function take(x: DubLine) {
  const done = after.lines.find((y) => y.line_id === x.line_id);
  if (!done) return;
  Object.assign(x, {
    status: "done",
    product_id: done.product_id,
    audio: structuredClone(done.audio),
    seconds: done.seconds,
  });
  fakeDub.takes.push(x.line_id);
  setTimeout(() =>
    injectEvent("product.updated", {
      product_id: x.product_id,
      series_id: "demo",
      slot: "line_audio",
      status: "adopted",
    }),
  );
}

function dub(body: DubRequest): Response {
  const dub = current();
  let lines = dub.lines;
  if (body.line_ids) {
    const unknown = body.line_ids.find((id) => !lines.some((x) => x.line_id === id));
    if (unknown) return error(404, "line_not_found", { id: unknown });
    lines = lines.filter((x) => body.line_ids?.includes(x.line_id));
  }
  const skipped: DubSkip[] = lines
    .filter((x) => x.status === "no_voice" || x.status === "voice_not_locked")
    .map((x) => ({
      line_id: x.line_id,
      code: x.status as DubSkip["code"],
      name: x.voice_name ?? x.speaker,
    }));
  const redo = body.line_ids
    ? ["missing", "stale", "failed", "done"]
    : ["missing", "stale", "failed"];
  const todo = lines.filter((x) => redo.includes(x.status));
  if (!body.dry_run) todo.forEach(take);
  return HttpResponse.json({
    estimate_usd: Math.round(chars(todo) * perChar * 1e6) / 1e6,
    lines: todo.length,
    jobs: body.dry_run ? [] : todo.map((x) => `job-dub-${x.line_id}-${fakeDub.takes.length}`),
    skipped,
  });
}

export function dubHandlers() {
  return [
    http.get("*/api/v1/episodes/:id/dub", ({ params }) =>
      params.id === before.episode_id
        ? HttpResponse.json(current())
        : HttpResponse.json({
            episode_id: params.id,
            lines: [],
            scenes: [],
            done: 0,
            total: 0,
          }),
    ),
    http.post("*/api/v1/episodes/:id/dub", async ({ params, request }) => {
      if (params.id !== before.episode_id) return error(404, "episode_not_found");
      return dub((await request.json()) as DubRequest);
    }),
    http.patch("*/api/v1/lines/:id/dub", async ({ params, request }) => {
      const x = current().lines.find((l) => l.line_id === params.id);
      if (!x) return error(404, "line_not_found", { id: params.id });
      const body = (await request.json()) as { emotion: string | null };
      x.emotion = body.emotion ?? x.tone_emotion;
      x.emotion_set = body.emotion !== null;
      return HttpResponse.json(x);
    }),
  ];
}
