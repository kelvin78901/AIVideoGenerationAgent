/**
 * Fake 剧本化 for page tests: each demo episode's script and its products as the Mock backend
 * answers them (`test/data/script.json`, written by tests/api/test_web_fixtures.py), and the
 * rewrites Mock proposes. Edits follow the backend's rules (`script/ops.py`): the text is
 * trimmed, a heading loses the 场号 typed in front, what changed is marked `edited`. Running an
 * episode's script writes one scene of its beats (the real one is the backend's Mock run).
 */
import { http, HttpResponse } from "msw";
import { z } from "zod";

import { injectEvent } from "@/api/events";
import type { Job } from "@/api/schemas/jobs";
import { ProductSchema, type Product } from "@/api/schemas/products";
import { ScriptSchema, type Script, type ScriptLine } from "@/api/schemas/script";
import { primaryModel } from "@/mocks/route";
import data from "@/test/data/script.json";
import { fakeResolve } from "@/test/fakes/config";
import { fakeEpisodes } from "@/test/fakes/episodes";

const demoScripts = z.record(z.string(), ScriptSchema).parse(data.scripts);
const demoProducts = data.products.map((p) => ProductSchema.parse(p));
const rewrites: Record<string, string> = data.rewrites;

/** State of the fake; `resetFakeScript()` (called by `backend()`) restores it. */
export const fakeScript = {
  scripts: structuredClone(demoScripts),
  products: structuredClone(demoProducts),
  /** Every edit sent, in order. */
  patches: [] as { id: string; text?: string; heading?: string }[],
  /** Every rewrite asked for, in order. */
  rewrites: [] as { id: string; model?: string; confirm_budget?: boolean }[],
  /** Answer rewrites with 409 `over_budget` until they come with `confirm_budget`. */
  overBudget: false,
};

export function resetFakeScript() {
  fakeScript.scripts = structuredClone(demoScripts);
  fakeScript.products = structuredClone(demoProducts);
  fakeScript.patches = [];
  fakeScript.rewrites = [];
  fakeScript.overBudget = false;
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

export function findBlock(id: string) {
  for (const script of Object.values(fakeScript.scripts)) {
    const scene = script.scenes.find((s) => s.id === id);
    const line = script.lines.find((l) => l.id === id);
    if (scene || line) return { script, scene, line };
  }
  return undefined;
}

type Edited = { script: Script } | { status: number; code: string };

/** `ops.edit_line`: trimmed, marked `edited` when it changed. */
function editLine(id: string, value: string | undefined): Edited {
  const found = findBlock(id);
  if (!found?.line) return { status: 404, code: "line_not_found" };
  const text = (value ?? "").trim();
  if (!text) return { status: 422, code: "line_empty" };
  if (text !== found.line.text) Object.assign(found.line, { text, edited: true });
  return { script: found.script };
}

/** `ops.edit_scene`: the 场号 typed in front is dropped. */
function editScene(id: string, value: string | undefined): Edited {
  const found = findBlock(id);
  if (!found?.scene) return { status: 404, code: "scene_not_found" };
  const heading = (value ?? "").replace(/^\s*场\s*\d+\s*/, "").trim();
  if (!heading) return { status: 422, code: "heading_empty" };
  if (heading !== found.scene.heading) Object.assign(found.scene, { heading, edited: true });
  return { script: found.script };
}

const answer = (r: Edited) =>
  "script" in r ? HttpResponse.json(r.script) : error(r.status, r.code);

/** The fake backend's 剧本化 products of a demo episode (merged into the MSW list), or null. */
export function scriptBackendFetch(url: URL): Response | null {
  const owner = url.searchParams.get("owner") ?? "";
  if (!url.pathname.endsWith("/products") || !owner.startsWith("episode:")) return null;
  const id = owner.slice("episode:".length);
  return HttpResponse.json(fakeScript.products.filter((p) => p.owner_id === id));
}

/** One scene of the episode's beats, as a first run writes it (enough for the page). */
function written(episodeId: string, n: number): Script {
  const ep = fakeEpisodes.list.find((e) => e.id === episodeId);
  const sceneId = `sc-${episodeId}-${n}`;
  const lines: ScriptLine[] = (ep?.beats ?? []).map((b, i) => ({
    id: `ln-${b.id}-${n}`,
    scene_id: sceneId,
    idx: i + 1,
    type: "action",
    character_id: null,
    character_name: null,
    tone: null,
    text: b.text,
    mood: null,
    duration_s: 3,
    overlay_shot: null,
    paras: b.paras,
    source_spans: b.source_spans,
    ai_added: false,
    cliffhanger: i === (ep?.beats.length ?? 0) - 1,
    edited: false,
  }));
  return {
    episode_id: episodeId,
    product_id: fakeScript.products.find((p) => p.owner_id === episodeId)?.id ?? null,
    version_id: `${episodeId}-v${n}`,
    adopted: true,
    source_id: "demo-src",
    scenes: [
      {
        id: sceneId,
        episode_id: episodeId,
        idx: ep?.scene_from ?? 1,
        heading: "夜　内　楼下便利店",
        location_id: null,
        time_of_day: "night",
        paras: [...new Set(lines.flatMap((l) => l.paras))],
        source_spans: [],
        edited: false,
      },
    ],
    lines,
  };
}

function run(p: Product, mode: string): Job {
  const n = p.versions.length + 1;
  const model = primaryModel(fakeResolve("script", null)?.values ?? null) ?? "deepseek/v4-pro";
  const versionId = `${p.id}-v${n}`;
  p.versions.push({
    ...structuredClone(p.versions[0] ?? fakeVersion(p)),
    id: versionId,
    n,
    origin: mode === "switch" ? "switch" : mode === "rerun" ? "rerun" : "run",
    model_key: model,
    parent_version_id: p.current_version_id,
  });
  p.current_version_id = versionId;
  p.adopted_version_id ??= versionId;
  p.status = "adopted";
  fakeScript.scripts[p.owner_id] = written(p.owner_id, n);
  const ep = fakeEpisodes.list.find((e) => e.id === p.owner_id);
  if (ep) Object.assign(ep, { script_status: "draft", stage: "in_progress" });
  setTimeout(() =>
    injectEvent("product.updated", { product_id: p.id, series_id: p.series_id, status: p.status }),
  );
  return {
    id: `job-${p.id}-${n}`,
    series_id: p.series_id,
    product_id: p.id,
    component_id: p.component_id,
    kind: "product.run",
    queue: `api:${model.split("/")[0]}`,
    state: "succeeded",
    priority: 0,
    attempt: 1,
    max_attempts: 3,
    params: { mode, model_key: model },
    result: { version_id: versionId, n },
    error: null,
    depends_on: [],
    est_cost_usd: 0.05,
    fallback_from_job_id: null,
    created_at: "2026-10-19T10:00:00Z",
    started_at: "2026-10-19T10:00:00Z",
    finished_at: "2026-10-19T10:00:01Z",
  };
}

function fakeVersion(p: Product): Product["versions"][number] {
  return {
    id: "",
    product_id: p.id,
    n: 0,
    origin: "run",
    parent_version_id: null,
    payload: {},
    files: [],
    content_hash: "",
    intent: "",
    compiled: "",
    compiled_overridden: false,
    model_key: null,
    where: "api",
    seed: null,
    params: {},
    qa: null,
    qa_pass: null,
    fallback_reason: null,
    stage: null,
    rating: null,
    cost_usd: 0.05,
    job_id: null,
    created_at: "2026-10-19T10:00:01Z",
    note: null,
  };
}

export function scriptHandlers() {
  return [
    http.get("*/api/v1/episodes/:id/script", ({ params }) => {
      const id = String(params.id);
      const script = fakeScript.scripts[id];
      return script ? HttpResponse.json(script) : error(404, "episode_not_found", { id });
    }),

    http.patch("*/api/v1/lines/:id", async ({ params, request }) => {
      const id = String(params.id);
      const body = (await request.json()) as { text?: string };
      fakeScript.patches.push({ id, ...body });
      return answer(editLine(id, body.text));
    }),

    http.patch("*/api/v1/scenes/:id", async ({ params, request }) => {
      const id = String(params.id);
      const body = (await request.json()) as { heading?: string };
      fakeScript.patches.push({ id, ...body });
      return answer(editScene(id, body.heading));
    }),

    http.post("*/api/v1/:kind/:id/rewrite", async ({ params, request }) => {
      const kind = String(params.kind);
      if (kind !== "lines" && kind !== "scenes") return undefined;
      const id = String(params.id);
      const body = (await request.json()) as { model?: string; confirm_budget?: boolean };
      fakeScript.rewrites.push({ id, ...body });
      const found = findBlock(id);
      const block = kind === "scenes" ? found?.scene : found?.line;
      if (!block) return error(404, kind === "scenes" ? "scene_not_found" : "line_not_found");
      if (fakeScript.overBudget && !body.confirm_budget)
        return error(409, "over_budget", { reason: "per_call", estimate_usd: 0.9, limit_usd: 0.8 });
      const route = primaryModel(fakeResolve("script", null)?.values ?? null);
      return HttpResponse.json({
        text: rewrites[id] ?? `${"text" in block ? block.text : block.heading}——换个说法。`,
        model_key: body.model ?? route ?? "deepseek/v4-pro",
      });
    }),

    http.get("*/api/v1/products/:id", ({ params }) => {
      const p = fakeScript.products.find((x) => x.id === params.id);
      return p ? HttpResponse.json(p) : undefined;
    }),

    http.post("*/api/v1/products/:id/run", async ({ params, request }) => {
      const p = fakeScript.products.find((x) => x.id === params.id);
      if (!p) return undefined;
      const body = (await request.json()) as { mode?: string };
      return HttpResponse.json(run(p, body.mode ?? "run"));
    }),
  ];
}
