import { http, HttpResponse } from "msw";

import { ApiError, put } from "@/api/client";
import type { StepId } from "@/api/schemas/episodes";
import { ApplyImpactRequestSchema, ImpactChangeSchema, type Impact } from "@/api/schemas/impact";
import { OutputSpecSchema } from "@/api/schemas/spec";
import { backendResponse } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { impactPreviews, scriptDownstream } from "@/mocks/fixtures/demo/impacts";
import { applyAssetUnlock, assetUnlockPreview } from "@/mocks/handlers/assets";
import { demoError, demoJson, v1 } from "@/mocks/http";

/** Changes the demo still answers (成片规格 and 素材, M4); every other kind is the backend's. */
const DEMO_KINDS = new Set(["spec_aspect", "asset_unlock"]);

let seq = 0;

/** The demo's steps after 剧本 show 「待更新 N」 in the nav. */
function markDemo(stale: Impact["stale"]): void {
  const steps = getDb().progress[EP1]?.steps;
  for (const [step, n] of Object.entries(stale) as [StepId, number][]) {
    const s = steps?.[step];
    if (s) s.stale += n;
  }
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
  // The backend previews the M2 changes (novel, bible, suggestions, beats, script); for a block
  // of the demo episode's script the demo adds what lies after it (shots, keyframes, videos).
  http.post(v1("/impact/preview"), async ({ request }) => {
    const forward = request.clone();
    const change = ImpactChangeSchema.safeParse(await request.json());
    if (!change.success) return demoError(422, "invalid_request", { issues: change.error.message });
    const { kind, target_id } = change.data;
    if (!DEMO_KINDS.has(kind)) {
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
    }
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
    const forward = request.clone();
    const body = ApplyImpactRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const { impact_id: id, action } = body.data;
    const impact = getDb().impacts.get(id);
    if (!impact) {
      // The backend's preview: it writes, marks and (确认并同步) reruns; the demo marks its own
      // downstream steps.
      const resp = await backendResponse(forward);
      const overlay = getDb().impactOverlays.get(id);
      if (resp?.ok && overlay) {
        getDb().impactOverlays.delete(id);
        if (action !== "undo") markDemo(overlay);
      }
      return relay(resp);
    }
    getDb().impacts.delete(id);
    // Undo drops the previewed change; nothing was written yet.
    if (action === "undo") return demoJson({ action, stale: {}, job_ids: [] });
    // The spec (M1) lives in the real backend; the demo impact confirms the aspect change.
    const { kind, target_id, patch: change } = impact.change;
    if (kind === "spec_aspect") {
      try {
        await put(
          `/series/${encodeURIComponent(target_id)}/spec?confirmed_impact=${encodeURIComponent(id)}`,
          OutputSpecSchema,
          change,
        );
      } catch (err) {
        if (err instanceof ApiError) return demoError(err.status, err.code, err.params);
        throw err;
      }
    }
    if (kind === "asset_unlock") applyAssetUnlock(target_id);
    markDemo(impact.stale);
    const jobs = action === "rerun" ? [`demo-job-impact-${id}`] : [];
    return demoJson({ action, stale: impact.stale, job_ids: jobs });
  }),
];
