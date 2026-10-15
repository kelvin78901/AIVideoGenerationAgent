import { http } from "msw";

import { ApiError, put } from "@/api/client";
import type { StepId } from "@/api/schemas/episodes";
import { ApplyImpactRequestSchema, ImpactChangeSchema } from "@/api/schemas/impact";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { impactPreviews } from "@/mocks/fixtures/demo/impacts";
import { applyAssetUnlock, assetUnlockPreview } from "@/mocks/handlers/assets";
import { applyScriptChange } from "@/mocks/handlers/script";
import { OutputSpecSchema } from "@/api/schemas/spec";
import { demoError, demoJson, v1 } from "@/mocks/http";

let seq = 0;

export const impactHandlers = [
  http.post(v1("/impact/preview"), async ({ request }) => {
    const change = ImpactChangeSchema.safeParse(await request.json());
    if (!change.success) return demoError(422, "invalid_request", { issues: change.error.message });
    const { kind, target_id } = change.data;
    const preview = impactPreviews[`${kind}:${target_id}`] ??
      (kind === "asset_unlock" ? assetUnlockPreview(target_id) : undefined) ?? {
        lines: [],
        unaffected: null,
        rerun_cost_usd: 0,
        stale: {},
      };
    const impact = { id: `demo-impact-${++seq}`, change: change.data, ...structuredClone(preview) };
    getDb().impacts.set(impact.id, impact);
    return demoJson(impact);
  }),

  http.post(v1("/impact/apply"), async ({ request }) => {
    const body = ApplyImpactRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const impact = getDb().impacts.get(body.data.impact_id);
    if (!impact) return demoError(404, "impact_not_found", { id: body.data.impact_id });
    getDb().impacts.delete(impact.id);
    const { action } = body.data;
    // Undo drops the previewed change; nothing was written yet.
    if (action === "undo") return demoJson({ action, stale: {}, job_ids: [] });
    // The spec lives in the real backend (M1); this demo impact only confirms the change.
    if (impact.change.kind === "spec_aspect") {
      const id = encodeURIComponent(impact.change.target_id);
      const path = `/series/${id}/spec?confirmed_impact=${encodeURIComponent(impact.id)}`;
      try {
        await put(path, OutputSpecSchema, impact.change.patch);
      } catch (err) {
        if (err instanceof ApiError) return demoError(err.status, err.code, err.params);
        throw err;
      }
    }
    if (impact.change.kind === "line_edit" || impact.change.kind === "scene_edit")
      applyScriptChange(impact.change);
    if (impact.change.kind === "asset_unlock") applyAssetUnlock(impact.change.target_id);
    // Mark (and for rerun, queue) the affected products: the nav shows 「待更新 N」.
    const steps = getDb().progress[EP1]?.steps;
    for (const [step, n] of Object.entries(impact.stale) as [StepId, number][]) {
      const s = steps?.[step];
      if (s) s.stale += n;
    }
    const jobs = action === "rerun" ? [`demo-job-impact-${impact.id}`] : [];
    return demoJson({ action, stale: impact.stale, job_ids: jobs });
  }),
];
