import { http } from "msw";

import { GenerateRulesPatchSchema, type GenerateLogEntry } from "@/api/schemas/generate";
import type { Job } from "@/api/schemas/jobs";
import type { Product, ProductVersion, QaCheck } from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";
import { getDb } from "@/mocks/db";
import { modelByKey } from "@/mocks/fixtures/demo/models";
import { demoCost } from "@/mocks/fixtures/demo/products";
import { qaResult } from "@/mocks/fixtures/demo/takes";
import { demoError, demoJson, v1 } from "@/mocks/http";
import { demoRoute, primaryModel } from "@/mocks/route";

export function shotOf(p: Product): Shot | undefined {
  return p.owner_type === "shot" ? getDb().shots.find((s) => s.id === p.owner_id) : undefined;
}

function videoProductOf(shot: Shot | undefined): Product | undefined {
  return shot?.video_product_id ? getDb().products[shot.video_product_id] : undefined;
}

/** A continuous shot waits until the shot it continues has an adopted take. */
export function waitingOn(shot: Shot): Shot | undefined {
  if (!shot.tail_from) return undefined;
  const tail = getDb().shots.find(
    (s) => s.episode_id === shot.episode_id && s.label === shot.tail_from,
  );
  return tail && !videoProductOf(tail)?.adopted_version_id ? tail : undefined;
}

export function adoptedTakeCount(episodeId: string): { done: number; total: number } {
  const list = getDb().shots.filter((s) => s.episode_id === episodeId);
  return {
    done: list.filter((s) => videoProductOf(s)?.adopted_version_id).length,
    total: list.length,
  };
}

/** Demo QA of a fresh take: every check that applies to the shot passes. */
export function demoTakeQa(shot: Shot, n: number): Pick<ProductVersion, "qa" | "qa_pass"> {
  const assets = getDb().assets.filter((a) => shot.asset_ids.includes(a.id));
  const speaks = shot.dialogue !== null && shot.audio_mode !== "none";
  const check = (metric: QaCheck["metric"], applies: boolean, value: number | null) => ({
    metric,
    value: applies ? value : null,
    text: null,
    issue: null,
    ok: applies || null,
  });
  const checks: QaCheck[] = [
    check(
      "face",
      assets.some((a) => a.kind === "character"),
      0.8 + (n % 3) * 0.02,
    ),
    check("lipsync", speaks, 7.6 + (n % 2) * 0.5),
    check("asr", speaks, 0),
    // Text pasted in post (method=composite) is not in the picture, so there is nothing to read.
    check(
      "ocr",
      assets.some((a) => a.text?.method === "model"),
      null,
    ),
    check("vlm", true, null),
  ];
  return { qa: qaResult(checks), qa_pass: true };
}

/** 运行记录 line for a finished take, like the backend's job listener would write. */
export function logTake(shot: Shot, version: ProductVersion): void {
  const fails = version.qa?.checks.filter((c) => c.ok === false).length ?? 0;
  const prefix = version.origin === "switch" ? "switch" : "take";
  const entry: GenerateLogEntry = {
    id: `demo-log-${version.id}`,
    at: version.created_at,
    shot_label: shot.label,
    message: {
      code: `${prefix}_${fails ? "fail" : "pass"}`,
      params: {
        model: version.model_key ?? "",
        take: version.n,
        cost_usd: version.cost_usd,
        fails,
      },
    },
    warn: fails > 0 || version.origin === "switch",
  };
  const log = (getDb().generateLog[shot.episode_id] ??= []);
  log.push(entry);
}

export const generateHandlers = [
  http.get(v1("/series/:id/generate-rules"), ({ params }) => {
    const rules = getDb().generateRules[String(params.id)];
    return rules ? demoJson(rules) : demoError(404, "series_not_found", { id: params.id });
  }),

  http.put(v1("/series/:id/generate-rules"), async ({ params, request }) => {
    const rules = getDb().generateRules[String(params.id)];
    if (!rules) return demoError(404, "series_not_found", { id: params.id });
    const body = GenerateRulesPatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    Object.assign(rules, body.data);
    return demoJson(rules);
  }),

  http.get(v1("/episodes/:id/generate-log"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().episodes.some((e) => e.id === id))
      return demoError(404, "episode_not_found", { id });
    return demoJson(getDb().generateLog[id] ?? []);
  }),

  // 2K 精修: queue the take on the 2K finishing component's route → job.
  http.post(v1("/versions/:id/upscale"), async ({ params }) => {
    const id = String(params.id);
    const product = Object.values(getDb().products).find((p) =>
      p.versions.some((v) => v.id === id),
    );
    if (!product || product.slot !== "video") return demoError(404, "version_not_found", { id });
    const model = primaryModel(await demoRoute("up")) ?? "comfy/seedvr2";
    const seconds = shotOf(product)?.duration_s ?? 4;
    const local = modelByKey(model)?.where === "local";
    const job: Job = {
      id: `demo-job-up-${id}-${Date.now()}`,
      series_id: product.series_id,
      product_id: product.id,
      component_id: "up",
      kind: "product.run",
      queue: local ? "gpu" : `api:${model.split("/")[0]}`,
      state: "queued",
      priority: 0,
      attempt: 0,
      max_attempts: 1,
      params: { version_id: id, model_key: model },
      result: null,
      error: null,
      depends_on: [],
      est_cost_usd: demoCost(model, seconds),
      fallback_from_job_id: null,
      created_at: new Date().toISOString(),
      started_at: null,
      finished_at: null,
    };
    // Not pushed into the real job list: the demo never finishes it (step 10 shows a toast).
    return demoJson(job);
  }),
];
