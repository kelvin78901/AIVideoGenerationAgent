import { http } from "msw";

import type { StepId } from "@/api/schemas/episodes";
import { ApplyImpactRequestSchema, ImpactChangeSchema } from "@/api/schemas/impact";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { impactPreviews } from "@/mocks/fixtures/demo/impacts";
import { demoError, demoJson, v1 } from "@/mocks/http";

let seq = 0;

export const impactHandlers = [
  http.post(v1("/impact/preview"), async ({ request }) => {
    const change = ImpactChangeSchema.safeParse(await request.json());
    if (!change.success) return demoError(422, "invalid_request", { issues: change.error.message });
    const preview = impactPreviews[`${change.data.kind}:${change.data.target_id}`] ?? {
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
    if (action === "undo") return demoJson({ action, stale: {}, job_ids: [] });
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
