import { http } from "msw";

import type { Job } from "@/api/schemas/jobs";
import {
  CompileRequestSchema,
  RunRequestSchema,
  SavePromptRequestSchema,
  VersionPatchSchema,
  type Product,
  type ProductVersion,
} from "@/api/schemas/products";
import { getDb } from "@/mocks/db";
import { demoTiming, emitDemoEvent } from "@/mocks/events";
import { llmModels, modelByKey } from "@/mocks/fixtures/demo/models";
import { demoCost, demoVersion } from "@/mocks/fixtures/demo/products";
import { compilePrompt } from "@/mocks/fixtures/demo/prompts";
import { keyframeCandidates } from "@/mocks/fixtures/demo/shots";
import { assetPayload } from "@/mocks/handlers/assets";
import { demoTakeQa, logTake, shotOf, waitingOn } from "@/mocks/handlers/generate";
import { demoError, demoJson, v1 } from "@/mocks/http";
import { demoRoute, primaryModel } from "@/mocks/route";

const notFound = (id: unknown) => demoError(404, "product_not_found", { id });
const DEFAULT_MODEL = "local/qwen3.6-27b";

function findVersion(id: string): { product: Product; version: ProductVersion } | undefined {
  for (const product of Object.values(getDb().products)) {
    const version = product.versions.find((v) => v.id === id);
    if (version) return { product, version };
  }
  return undefined;
}

function currentVersion(p: Product): ProductVersion | undefined {
  return p.versions.find((v) => v.id === p.current_version_id) ?? p.versions.at(-1);
}

/** Status after a change: locked > adopted > ready (SPEC 4.2). */
function settle(p: Product): void {
  p.status = p.locked_hash ? "locked" : p.adopted_version_id ? "adopted" : "ready";
}

/** Cost units of one run: seconds for a video take, candidates for images (demoCost). */
function costUnits(p: Product): number {
  if (p.slot === "video") return shotOf(p)?.duration_s ?? 4;
  return p.slot === "keyframe" ? 3 : 4;
}

function demoJob(p: Product, modelKey: string, mode: string): Job {
  const local = modelByKey(modelKey)?.where === "local";
  return {
    id: `demo-job-${p.id}-${Date.now()}`,
    series_id: p.series_id,
    product_id: p.id,
    component_id: p.component_id,
    kind: "product.run",
    queue: local ? "gpu" : `api:${modelKey.split("/")[0]}`,
    state: "queued",
    priority: 0,
    attempt: 0,
    max_attempts: 1,
    params: { mode, model_key: modelKey },
    result: null,
    error: null,
    depends_on: [],
    est_cost_usd: demoCost(modelKey, costUnits(p)),
    fallback_from_job_id: null,
    created_at: new Date().toISOString(),
    started_at: null,
    finished_at: null,
  };
}

/** 「不满意换一个」 without a model: the next one after the current (SPEC 7.4 alt_order). */
function nextModel(current: string): string {
  const i = llmModels.findIndex((m) => m.key === current);
  return llmModels[(i + 1) % llmModels.length]?.key ?? current;
}

/** The model a plain run uses: the component's configured route (Inspector「运行设置」). */
async function routeModel(p: Product): Promise<string> {
  return (
    primaryModel(await demoRoute(p.component_id)) ??
    currentVersion(p)?.model_key ??
    p.prompt?.model_key ??
    DEFAULT_MODEL
  );
}

/** `estimate` is computed on read, so it follows config changes (hard rule 6). */
async function withEstimate(p: Product): Promise<Product> {
  if (p.running) return p;
  const model = await routeModel(p);
  p.estimate = {
    model_key: model,
    where: modelByKey(model)?.where ?? "api",
    cost_usd: demoCost(model, costUnits(p)),
    seconds: p.estimate?.seconds ?? null,
  };
  return p;
}

const hhmm = (d: Date) =>
  `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

/** Appends the version(s) of a finished demo run and announces them like the backend would. */
function finishRun(
  p: Product,
  run: { jobId: string; mode: Product["versions"][number]["origin"]; model: string },
  opts: { count: number; intent: string; compiled: string | undefined },
): void {
  const parent = currentVersion(p);
  const created: ProductVersion[] = [];
  for (let i = 0; i < opts.count; i++) {
    const version = demoVersion(p.id, p.component_id, {
      n: p.versions.length + 1,
      origin: run.mode,
      model: run.model,
      at: new Date().toISOString(),
      parent: parent?.id ?? null,
      intent: opts.intent,
      compiled: opts.compiled,
      payload: assetPayload(p) ?? (p.slot === "keyframe" ? keyframeCandidates() : parent?.payload),
    });
    version.job_id = run.jobId;
    const shot = p.slot === "video" ? shotOf(p) : undefined;
    if (shot) {
      Object.assign(version, demoTakeQa(shot, version.n), {
        payload: { duration_s: shot.duration_s, resolution: "768p" },
        cost_usd: demoCost(run.model, shot.duration_s),
      });
      logTake(shot, version);
    }
    p.versions.push(version);
    created.push(version);
  }
  const last = created[created.length - 1];
  if (!last) return;
  p.current_version_id = last.id;
  p.running = null;
  settle(p);
  // A first script for an episode makes it a draft (剧本草稿).
  if (p.slot === "script" && p.owner_type === "episode") {
    const ep = getDb().episodes.find((e) => e.id === p.owner_id);
    if (ep?.script_status === "none") ep.script_status = "draft";
  }
  for (const v of created) {
    emitDemoEvent("version.created", {
      product_id: p.id,
      version_id: v.id,
      n: v.n,
      origin: v.origin,
    });
  }
  emitDemoEvent("product.updated", { product_id: p.id, series_id: p.series_id, status: p.status });
  emitDemoEvent("toast", {
    level: "success",
    code: "version_created",
    params: {
      n: last.n,
      model: modelByKey(run.model)?.display ?? run.model,
      time: hhmm(new Date()),
    },
  });
}

export const productHandlers = [
  // ?owner=<type>:<id>&component=<id>
  http.get(v1("/products"), async ({ request }) => {
    const q = new URL(request.url).searchParams;
    const owner = q.get("owner");
    const component = q.get("component");
    const list = Object.values(getDb().products).filter(
      (p) =>
        (!owner || `${p.owner_type}:${p.owner_id}` === owner) &&
        (!component || p.component_id === component),
    );
    return demoJson(await Promise.all(list.map(withEstimate)));
  }),

  http.get(v1("/products/:id"), async ({ params }) => {
    const p = getDb().products[String(params.id)];
    return p ? demoJson(await withEstimate(p)) : notFound(params.id);
  }),

  http.post(v1("/products/:id/run"), async ({ params, request }) => {
    const p = getDb().products[String(params.id)];
    if (!p) return notFound(params.id);
    const body = RunRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    if (p.running) return demoError(409, "product_busy", { id: p.id });
    // A continuous shot starts from the last frame of a shot that has no adopted take yet.
    const shot = shotOf(p);
    const tail = p.slot === "video" && shot ? waitingOn(shot) : undefined;
    if (tail) return demoError(409, "upstream_not_adopted", { id: tail.label });

    const req = body.data;
    // 重跑 uses the configured route; 不满意换一个 moves on from the version on screen.
    const base =
      req.mode === "switch"
        ? (currentVersion(p)?.model_key ?? (await routeModel(p)))
        : await routeModel(p);
    const model = req.model ?? (req.mode === "switch" ? nextModel(base) : base);
    if (!modelByKey(model)) return demoError(404, "unknown_model", { key: model });

    const job = demoJob(p, model, req.mode);
    const intent = req.intent ?? p.prompt?.intent ?? currentVersion(p)?.intent ?? "";
    // A hand-edited compiled layer is sent as is (also the saved one on a plain rerun);
    // otherwise, and always when switching models, compile for the target model.
    const saved = p.prompt;
    const keepSaved =
      req.mode !== "switch" && req.intent === undefined && saved?.compiled_overridden === true;
    const compiled = req.compiled ?? (keepSaved ? saved.compiled : undefined);
    p.prompt = {
      intent,
      compiled: compiled ?? compilePrompt(p.component_id, intent, model),
      compiled_overridden: compiled !== undefined,
      model_key: model,
    };
    p.running = { job_id: job.id, model_key: model };
    p.status = "running";
    setTimeout(
      () =>
        finishRun(
          p,
          { jobId: job.id, mode: req.mode, model },
          { count: req.count ?? 1, intent, compiled },
        ),
      demoTiming.runMs,
    );
    return demoJson(job);
  }),

  http.post(v1("/versions/:id/set-current"), ({ params }) => {
    const found = findVersion(String(params.id));
    if (!found) return demoError(404, "version_not_found", { id: params.id });
    found.product.current_version_id = found.version.id;
    return demoJson(found.product);
  }),

  http.post(v1("/versions/:id/adopt"), ({ params }) => {
    const found = findVersion(String(params.id));
    if (!found) return demoError(404, "version_not_found", { id: params.id });
    const { product: p, version } = found;
    if (p.locked_hash) return demoError(409, "product_locked", { id: p.id });
    // One adopted version per product: adopting replaces the previous one.
    p.adopted_version_id = version.id;
    p.current_version_id = version.id;
    settle(p);
    return demoJson(p);
  }),

  // 取消采纳 (候选墙): nothing downstream uses this product until another version is adopted.
  http.post(v1("/products/:id/unadopt"), ({ params }) => {
    const p = getDb().products[String(params.id)];
    if (!p) return notFound(params.id);
    if (p.locked_hash) return demoError(409, "product_locked", { id: p.id });
    p.adopted_version_id = null;
    settle(p);
    return demoJson(p);
  }),

  // 数字键打分 on the candidate wall.
  http.patch(v1("/versions/:id"), async ({ params, request }) => {
    const found = findVersion(String(params.id));
    if (!found) return demoError(404, "version_not_found", { id: params.id });
    const body = VersionPatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    Object.assign(found.version, body.data);
    return demoJson(found.product);
  }),

  http.post(v1("/products/:id/lock"), ({ params }) => {
    const p = getDb().products[String(params.id)];
    if (!p) return notFound(params.id);
    const adopted = p.versions.find((v) => v.id === p.adopted_version_id);
    if (!adopted) return demoError(409, "nothing_adopted", { id: p.id });
    p.locked_hash = adopted.content_hash;
    settle(p);
    return demoJson(p);
  }),

  http.post(v1("/products/:id/unlock"), ({ params }) => {
    const p = getDb().products[String(params.id)];
    if (!p) return notFound(params.id);
    p.locked_hash = null;
    settle(p);
    return demoJson(p);
  }),

  http.put(v1("/products/:id/prompt"), async ({ params, request }) => {
    const p = getDb().products[String(params.id)];
    if (!p) return notFound(params.id);
    const body = SavePromptRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const model = p.prompt?.model_key ?? currentVersion(p)?.model_key ?? DEFAULT_MODEL;
    p.prompt = {
      intent: body.data.intent,
      compiled: body.data.compiled ?? compilePrompt(p.component_id, body.data.intent, model),
      compiled_overridden: body.data.compiled !== null,
      model_key: model,
    };
    return demoJson(p);
  }),

  http.post(v1("/products/:id/compile"), async ({ params, request }) => {
    const p = getDb().products[String(params.id)];
    if (!p) return notFound(params.id);
    const body = CompileRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const model = body.data.model ?? p.prompt?.model_key ?? DEFAULT_MODEL;
    return demoJson({
      compiled: compilePrompt(p.component_id, body.data.intent, model),
      model_key: model,
    });
  }),
];
