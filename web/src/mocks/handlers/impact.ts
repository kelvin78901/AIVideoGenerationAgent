import { http, HttpResponse } from "msw";

import type { StepId } from "@/api/schemas/episodes";
import { ApplyImpactRequestSchema, ImpactChangeSchema, type Impact } from "@/api/schemas/impact";
import { backendResponse } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { scriptDownstream } from "@/mocks/fixtures/demo/impacts";
import { demoError, demoJson, v1 } from "@/mocks/http";

/** The demo's 生成 step shows 「待更新 N」 in the nav. */
function markDemo(stale: Impact["stale"]): void {
  const steps = getDb().progress[EP1];
  const n = stale.generate;
  if (steps && n) steps.generate.stale += n;
}

/** The backend's answer as is; a network error when it is down (as without MSW). */
async function relay(resp: Response | null) {
  if (!resp) return HttpResponse.error();
  const text = await resp.text();
  return new HttpResponse(text, {
    status: resp.status,
    headers: { "Content-Type": resp.headers.get("Content-Type") ?? "application/json" },
  });
}

export const impactHandlers = [
  // The backend previews every change (shots and keyframes included since M4); for a block of
  // the demo episode's script the demo adds the videos after it (M5).
  http.post(v1("/impact/preview"), async ({ request }) => {
    const forward = request.clone();
    const change = ImpactChangeSchema.safeParse(await request.json());
    if (!change.success) return demoError(422, "invalid_request", { issues: change.error.message });
    const { kind, target_id } = change.data;
    const resp = await backendResponse(forward);
    if (!resp?.ok) return relay(resp);
    const real = (await resp.json()) as Impact;
    const extra = scriptDownstream[`${kind}:${target_id}`];
    if (!extra) return HttpResponse.json(real);
    getDb().impactOverlays.set(real.id, extra.stale);
    const stale = { ...real.stale };
    for (const [step, n] of Object.entries(extra.stale) as [StepId, number][])
      stale[step] = (stale[step] ?? 0) + n;
    return demoJson({
      ...real,
      lines: [...real.lines, ...structuredClone(extra.lines)],
      rerun_cost_usd: Math.round((real.rerun_cost_usd + extra.rerun_cost_usd) * 100) / 100,
      stale,
    });
  }),

  // The backend writes, marks and (确认并同步) reruns; the demo marks its own 生成 step.
  http.post(v1("/impact/apply"), async ({ request }) => {
    const forward = request.clone();
    const body = ApplyImpactRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const { impact_id: id, action } = body.data;
    const resp = await backendResponse(forward);
    const overlay = getDb().impactOverlays.get(id);
    if (resp?.ok && overlay) {
      getDb().impactOverlays.delete(id);
      if (action !== "undo") markDemo(overlay);
    }
    return relay(resp);
  }),
];
