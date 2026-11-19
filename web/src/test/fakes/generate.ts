/**
 * Fake 生成 for page tests: episode 1's video products with the demo's takes, the auto rules,
 * the run log and the header's spend as the Mock backend answers them once 分镜 is confirmed
 * (`test/data/generate.json`, written by tests/api/test_web_fixtures.py), following the
 * backend's rules (`pipeline/components/vid.py`, `pipeline/generate.py`) as far as the pages
 * need them:
 * - a run needs 分镜 confirmed (409 `storyboard_not_confirmed`) and, for a continuous shot, an
 *   adopted take of the shot it continues (409 `upstream_not_adopted`); the first run makes
 *   `takes_per_shot` takes, 「再出一条」 one, each on the configured route, with a run-log line;
 *   「用 API 出终版」 one 2K take on Regenerate-2K whose parent is the draft;
 * - 采纳 (one per shot), 取消采纳, 打分; 生成确认 needs every shot adopted (409
 *   `takes_not_adopted`) and locks them;
 * - a take's 2K 精修, 口型修复 (409 `lipsync_no_dialogue` for a shot nobody speaks in), 视频局部修复
 *   and 重新质检 (M6) are queued on their route and recorded in `repairs`; they never finish;
 * - the 生成 badge: 未开始 before 分镜确认, then the shots with an adopted take.
 *
 * The other tests see the same takes, with 分镜 still in progress (`test/fakes/shots.ts`);
 * `confirmFakeStoryboard()` puts the shots where the seeded demo has them.
 */
import { http, HttpResponse } from "msw";
import { z } from "zod";

import { injectEvent } from "@/api/events";
import {
  GenerateLogEntrySchema,
  GenerateRulesPatchSchema,
  GenerateRulesSchema,
  WorkflowRuleSchema,
  WorkflowRulesSchema,
  type GenerateLogEntry,
} from "@/api/schemas/generate";
import type { Job } from "@/api/schemas/jobs";
import { MetricsSummarySchema } from "@/api/schemas/metrics";
import {
  ProductSchema,
  VersionPatchSchema,
  type Product,
  type ProductVersion,
  type RunRequest,
} from "@/api/schemas/products";
import { ShotSchema, type Shot } from "@/api/schemas/shots";
import { primaryModel } from "@/mocks/route";
import data from "@/test/data/generate.json";
import { fakeResolve } from "@/test/fakes/config";
import { fakeShots, fakeStoryboardGate } from "@/test/fakes/shots";

const EPISODE = "demo-e1";
const demoShots = z.array(ShotSchema).parse(data.shots);
const demoVideos = data.videos.map((p) => ProductSchema.parse(p));
const demoRules = GenerateRulesSchema.parse(data.rules);
const demoWorkflowRules = WorkflowRulesSchema.parse(data.workflow_rules);
const demoLog = z.array(GenerateLogEntrySchema).parse(data.log);
const demoSummary = MetricsSummarySchema.parse(data.summary);
/** What one Mock take costs here: local free, the H3 API $0.11 a second (¥0.80). */
const API_PER_SECOND = 0.11;
const FINAL_MODEL = "minimax/h3-regenerate-2k";

/** State of the fake; `resetFakeGenerate()` (called by `backend()`) restores it. */
export const fakeGenerate = {
  videos: structuredClone(demoVideos),
  rules: structuredClone(demoRules),
  /** 按镜头选工作流 of the demo series. */
  workflowRules: structuredClone(demoWorkflowRules),
  log: structuredClone(demoLog),
  summary: structuredClone(demoSummary),
  /** Episodes whose 生成确认 is confirmed. */
  confirmed: new Set<string>(),
  /** Every run asked for, in order. */
  runs: [] as ({ id: string } & RunRequest)[],
  /** Every finishing, repair or QA asked of a take (M6), in order. */
  repairs: [] as TakeRepair[],
};

/** What was asked of a take: `where` of a lip-sync repair, the mask's size and the prompt of a
 * region repair. */
export interface TakeRepair {
  kind: "upscale" | "lipsync" | "inpaint" | "qa";
  version: string;
  where?: string | null;
  prompt?: string | null;
  mask?: number;
}

export function resetFakeGenerate() {
  fakeGenerate.videos = structuredClone(demoVideos);
  fakeGenerate.rules = structuredClone(demoRules);
  fakeGenerate.workflowRules = structuredClone(demoWorkflowRules);
  fakeGenerate.log = structuredClone(demoLog);
  fakeGenerate.summary = structuredClone(demoSummary);
  fakeGenerate.confirmed = new Set();
  fakeGenerate.runs = [];
  fakeGenerate.repairs = [];
}

/** 分镜确认 as the seeded demo has it: every shot confirmed, the plan locked. */
export function confirmFakeStoryboard() {
  fakeShots.shots = structuredClone(demoShots);
  fakeStoryboardGate(EPISODE, "confirm");
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

const videoById = (id: unknown) => fakeGenerate.videos.find((p) => p.id === id);
const shotOf = (p: Product): Shot | undefined => fakeShots.shots.find((s) => s.id === p.owner_id);
const videoOf = (s: Shot | undefined) =>
  s ? fakeGenerate.videos.find((p) => p.id === s.video_product_id) : undefined;
const findVersion = (id: unknown) => {
  for (const product of fakeGenerate.videos) {
    const version = product.versions.find((v) => v.id === id);
    if (version) return { product, version };
  }
  return undefined;
};

function settle(p: Product) {
  p.status = p.locked_hash ? "locked" : p.adopted_version_id ? "adopted" : "ready";
}

function announce(p: Product, created: ProductVersion[] = []) {
  setTimeout(() => {
    for (const v of created)
      injectEvent("version.created", {
        product_id: p.id,
        version_id: v.id,
        n: v.n,
        origin: v.origin,
      });
    injectEvent("product.updated", { product_id: p.id, series_id: p.series_id, status: p.status });
  });
}

/** 生成 n / m of episode 1 (`ShotService.generate_badge`), or null for another episode. */
export function fakeGenerateBadge(episodeId: string) {
  if (episodeId !== EPISODE) return null;
  if (!fakeShots.confirmed.has(episodeId))
    return { state: "not_started" as const, done: null, total: null, stale: 0 };
  const list = fakeShots.shots;
  return {
    state: fakeGenerate.confirmed.has(episodeId)
      ? ("confirmed" as const)
      : ("in_progress" as const),
    done: list.filter((s) => videoOf(s)?.adopted_version_id).length,
    total: list.length,
    stale: 0,
  };
}

/** 生成确认 / 重新打开 (scope: the episode); the refusal, or null. */
export function fakeTakesGate(episodeId: string, action: string): Response | null {
  if (episodeId !== EPISODE) return error(404, "episode_not_found", { id: episodeId });
  const videos = fakeShots.shots.map(videoOf).filter((p): p is Product => !!p);
  if (action !== "confirm") {
    fakeGenerate.confirmed.delete(episodeId);
    for (const p of videos) {
      p.locked_hash = null;
      settle(p);
    }
    return null;
  }
  const missing = fakeShots.shots.filter((s) => !videoOf(s)?.adopted_version_id);
  if (missing.length)
    return error(409, "takes_not_adopted", {
      count: missing.length,
      labels: missing.map((s) => s.label).join("、"),
    });
  fakeGenerate.confirmed.add(episodeId);
  for (const p of videos) {
    p.locked_hash = `sha256:${p.adopted_version_id ?? ""}`;
    settle(p);
  }
  return null;
}

function logLine(shot: Shot, v: ProductVersion) {
  const code = v.stage === "final" ? "final" : v.origin === "switch" ? "switch" : "take";
  const entry: GenerateLogEntry = {
    id: `v-${v.id}`,
    at: v.created_at,
    shot_label: shot.label,
    message: {
      code,
      params: { model: v.model_key ?? "", take: v.n, cost_usd: v.cost_usd, fails: 0 },
    },
    warn: v.origin === "switch",
  };
  fakeGenerate.log.push(entry);
}

/** A take like the seed's (the shot's first take as a template), on `model`. */
function addTake(
  p: Product,
  shot: Shot,
  v: { origin: ProductVersion["origin"]; model: string; parent: string | null; final: boolean },
): ProductVersion {
  const template = demoVideos.find((x) => x.versions.length)?.versions[0];
  if (!template) throw new Error("generate.json has no takes");
  const n = p.versions.length + 1;
  const id = `${p.id}-v${n}`;
  const local = v.model.startsWith("comfy/");
  const seconds = shot.duration_s;
  const version: ProductVersion = {
    ...structuredClone(template),
    id,
    product_id: p.id,
    n,
    origin: v.origin,
    parent_version_id: v.parent,
    content_hash: `sha256:${id}`,
    model_key: v.model,
    where: local ? "local" : "api",
    stage: v.final ? "final" : local ? "draft" : null,
    fallback_reason: null,
    rating: null,
    cost_usd: local ? 0 : Math.round(API_PER_SECOND * seconds * 10000) / 10000,
    job_id: `job-${id}`,
    created_at: "2026-10-22T10:00:00Z",
    payload: {
      ...template.payload,
      duration_s: seconds - 0.3,
      resolution: v.final ? "2k" : "768p",
    },
    files: template.files.map((f) => ({ ...f, sha256: `${id}-${f.role}` })),
  };
  p.versions.push(version);
  p.current_version_id = id;
  logLine(shot, version);
  return version;
}

function job(p: Product, id: string, model: string, mode: string, cost: number): Job {
  return {
    id: `job-${id}`,
    series_id: p.series_id,
    product_id: p.id,
    component_id: p.component_id,
    kind: "product.run",
    queue: model.startsWith("comfy/") ? "gpu" : `api:${model.split("/")[0]}`,
    state: "succeeded",
    priority: 0,
    attempt: 1,
    max_attempts: 3,
    params: { mode, model_key: model },
    result: { version_id: id },
    error: null,
    depends_on: [],
    est_cost_usd: cost,
    fallback_from_job_id: null,
    created_at: "2026-10-22T10:00:00Z",
    started_at: "2026-10-22T10:00:00Z",
    finished_at: "2026-10-22T10:00:01Z",
  };
}

function run(p: Product, body: RunRequest): Response {
  const shot = shotOf(p);
  if (!shot) return error(404, "shot_not_found", { id: p.owner_id });
  if (!fakeShots.confirmed.has(shot.episode_id))
    return error(409, "storyboard_not_confirmed", { id: shot.episode_id });
  if (shot.tail_from) {
    const upstream = fakeShots.shots.find((s) => s.label === shot.tail_from);
    if (!videoOf(upstream)?.adopted_version_id)
      return error(409, "upstream_not_adopted", { id: shot.tail_from });
  }
  fakeGenerate.runs.push({ id: p.id, ...body });
  const source = body.params?.source_version_id;
  const route = fakeResolve("vid", `shot:${shot.id}`)?.values ?? null;
  const model = source ? FINAL_MODEL : (body.model ?? primaryModel(route) ?? "comfy/h3");
  const count = source
    ? 1
    : p.versions.length
      ? (body.count ?? 1)
      : fakeGenerate.rules.takes_per_shot;
  const created = Array.from({ length: count }, () =>
    addTake(p, shot, { origin: body.mode, model, parent: source ?? null, final: !!source }),
  );
  settle(p);
  announce(p, created);
  const last = created[created.length - 1];
  return HttpResponse.json(
    job(
      p,
      last?.id ?? p.id,
      model,
      body.mode,
      created.reduce((n, v) => n + v.cost_usd, 0),
    ),
  );
}

/** What the MSW demo reads from the backend (`mocks/handlers/shots.ts:demoVideos`, the summary
 * it lays the dashboard over). */
export function generateBackendFetch(url: URL): Response | null {
  if (url.pathname.endsWith("/api/v1/products") && url.searchParams.get("component") === "vid")
    return HttpResponse.json(fakeGenerate.videos);
  if (url.pathname.endsWith("/api/v1/metrics/summary")) {
    // The series: its three episodes' budgets ($15 each).
    if (url.searchParams.get("scope") !== "series") return HttpResponse.json(fakeGenerate.summary);
    const budget = (fakeGenerate.summary.budget_usd ?? 0) * 3;
    return HttpResponse.json({ ...fakeGenerate.summary, scope: "series", budget_usd: budget });
  }
  return null;
}

/** The video products of an owner (`shot:<id>`). */
export function fakeVideoProducts(owner: string): Product[] {
  const [kind, id] = owner.split(":");
  return kind === "shot" ? fakeGenerate.videos.filter((p) => p.owner_id === id) : [];
}

export function generateHandlers() {
  return [
    http.get("*/api/v1/products", ({ request }) => {
      const q = new URL(request.url).searchParams;
      return !q.get("owner") && q.get("component") === "vid"
        ? HttpResponse.json(fakeGenerate.videos)
        : undefined;
    }),

    http.get("*/api/v1/products/:id", ({ params }) => {
      const p = videoById(params.id);
      return p ? HttpResponse.json(p) : undefined;
    }),

    http.post("*/api/v1/products/:id/run", async ({ params, request }) => {
      const p = videoById(params.id);
      if (!p) return undefined;
      return run(p, (await request.json()) as RunRequest);
    }),

    http.post("*/api/v1/versions/:id/adopt", ({ params }) => {
      const found = findVersion(params.id);
      if (!found) return undefined;
      const { product: p, version } = found;
      if (p.locked_hash) return error(409, "product_locked", { id: p.id });
      p.adopted_version_id = version.id;
      p.current_version_id = version.id;
      settle(p);
      announce(p);
      return HttpResponse.json(p);
    }),

    // 2K 精修, 口型修复, 视频局部修复 and 重新质检 of a take (M6): queued on the component's
    // route; the fake never finishes them.
    http.post("*/api/v1/versions/:id/:op", async ({ params, request }) => {
      const op = String(params.op);
      const component = { upscale: "up", lipsync: "lip", inpaint: "vinpaint", qa: "qa" }[op];
      const found = findVersion(params.id);
      if (!component || !found) return undefined;
      const repair: TakeRepair = { kind: op as TakeRepair["kind"], version: found.version.id };
      let where: string | undefined;
      if (op === "inpaint") {
        const form = await request.formData();
        const mask = form.get("mask");
        const prompt = form.get("prompt");
        repair.prompt = typeof prompt === "string" ? prompt : null;
        repair.mask = typeof mask === "object" && mask ? mask.size : 0;
      } else if (op === "lipsync") {
        const text = await request.text();
        const body = (text ? JSON.parse(text) : {}) as { where?: string };
        where = body.where;
        repair.where = where ?? null;
        if (!shotOf(found.product)?.dialogue)
          return error(409, "lipsync_no_dialogue", { id: found.product.id });
      }
      const values = fakeResolve(component, null)?.values ?? null;
      const model =
        (where === "api" ? values?.api_model : where === "local" ? values?.local_model : null) ??
        primaryModel(values) ??
        "comfy/seedvr2";
      fakeGenerate.repairs.push(repair);
      return HttpResponse.json({
        ...job(found.product, `${op}-${found.version.id}`, String(model), "run", 0),
        component_id: component,
        state: "queued",
        result: null,
      });
    }),

    http.post("*/api/v1/products/:id/unadopt", ({ params }) => {
      const p = videoById(params.id);
      if (!p) return undefined;
      if (p.locked_hash) return error(409, "product_locked", { id: p.id });
      p.adopted_version_id = null;
      settle(p);
      announce(p);
      return HttpResponse.json(p);
    }),

    http.patch("*/api/v1/versions/:id", async ({ params, request }) => {
      const found = findVersion(params.id);
      if (!found) return undefined;
      const body = VersionPatchSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      Object.assign(found.version, body.data);
      return HttpResponse.json(found.product);
    }),

    http.get("*/api/v1/series/:id/generate-rules", ({ params }) =>
      params.id === "demo" ? HttpResponse.json(fakeGenerate.rules) : error(404, "series_not_found"),
    ),

    http.put("*/api/v1/series/:id/generate-rules", async ({ params, request }) => {
      if (params.id !== "demo") return error(404, "series_not_found");
      const body = GenerateRulesPatchSchema.strict().safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const { thresholds, qa_on, reset_qa, ...rest } = body.data;
      const rules = fakeGenerate.rules;
      Object.assign(rules, rest);
      if (reset_qa) {
        rules.thresholds = structuredClone(demoRules.thresholds);
        rules.qa_on = structuredClone(demoRules.qa_on);
      }
      Object.assign(rules.thresholds, thresholds);
      Object.assign(rules.qa_on, qa_on);
      return HttpResponse.json(rules);
    }),

    http.get("*/api/v1/series/:id/workflow-rules", ({ params }) =>
      params.id === "demo"
        ? HttpResponse.json(fakeGenerate.workflowRules)
        : error(404, "series_not_found"),
    ),

    http.put("*/api/v1/series/:id/workflow-rules", async ({ params, request }) => {
      if (params.id !== "demo") return error(404, "series_not_found");
      const body = z
        .object({ rules: z.array(WorkflowRuleSchema.strict()), suggest: z.boolean() })
        .strict()
        .safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const table = fakeGenerate.workflowRules;
      const bad = body.data.rules.find((r) => !table.models.includes(r.model));
      if (bad) return error(422, "workflow_rule_model", { model: bad.model });
      fakeGenerate.workflowRules = { ...table, ...body.data, saved: true };
      return HttpResponse.json(fakeGenerate.workflowRules);
    }),

    http.delete("*/api/v1/series/:id/workflow-rules", ({ params }) => {
      if (params.id !== "demo") return error(404, "series_not_found");
      fakeGenerate.workflowRules = structuredClone(demoWorkflowRules);
      return HttpResponse.json(fakeGenerate.workflowRules);
    }),

    http.post("*/api/v1/gates/takes/:action", async ({ params, request }) => {
      const body = (await request.json()) as { scope_id?: string };
      const scope = String(body.scope_id ?? "");
      const action = String(params.action);
      const refused = fakeTakesGate(scope, action);
      return (
        refused ??
        HttpResponse.json({
          id: `gate-takes-${action}`,
          gate: "takes",
          scope_id: scope,
          action,
          decided_at: "2026-10-22T10:00:00Z",
        })
      );
    }),

    http.get("*/api/v1/episodes/:id/generate-log", ({ params }) =>
      HttpResponse.json(params.id === EPISODE ? fakeGenerate.log : []),
    ),
  ];
}
