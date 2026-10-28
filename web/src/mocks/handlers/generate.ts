import { http } from "msw";

import type { Job } from "@/api/schemas/jobs";
import { modelByKey } from "@/mocks/fixtures/demo/models";
import { demoCost } from "@/mocks/fixtures/demo/products";
import { demoVideos } from "@/mocks/handlers/shots";
import { demoError, demoJson, v1 } from "@/mocks/http";
import { demoRoute, primaryModel } from "@/mocks/route";

/**
 * The generate page's takes, rules, run log, 取消采纳 and ratings are the backend's (M5); 2K 精修
 * stays the demo's until M6.
 */
export const generateHandlers = [
  // 2K 精修: queue the take on the 2K finishing component's route → job.
  http.post(v1("/versions/:id/upscale"), async ({ params, request }) => {
    const id = String(params.id);
    const product = (await demoVideos(request)).find((p) => p.versions.some((v) => v.id === id));
    const version = product?.versions.find((v) => v.id === id);
    if (!product || !version) return demoError(404, "version_not_found", { id });
    const model = primaryModel(await demoRoute("up")) ?? "comfy/seedvr2";
    const seconds = typeof version.payload.duration_s === "number" ? version.payload.duration_s : 4;
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
    // Not pushed into the real job list: the demo never finishes it (a toast says it went).
    return demoJson(job);
  }),
];
