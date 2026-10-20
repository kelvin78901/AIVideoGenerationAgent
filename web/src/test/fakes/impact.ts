/**
 * Fake gates (小说, 剧本) and impact previews for page tests, following the backend's rules
 * (`pipeline/gates.py`, `pipeline/impact.py`) as far as the pages need them: confirming flips
 * the step badges and the script status; a preview of an edit to confirmed work lists
 * 「已确认的 … 会改成新内容」, and 只改这里 / 确认并同步 write the edit (the sync's reruns are the
 * backend's; here they only show up as job ids).
 */
import { http, HttpResponse } from "msw";

import { ApplyImpactRequestSchema, ImpactChangeSchema, type Impact } from "@/api/schemas/impact";
import { fakeBible } from "@/test/fakes/bible";
import { fakeEpisodes } from "@/test/fakes/episodes";
import { editLine, editScene, findBlock } from "@/test/fakes/script";

type Line = Impact["lines"][number];

/** State of the fake; `resetFakeImpact()` (called by `backend()`) restores it. */
export const fakeImpact = {
  previews: new Map<string, Impact>(),
  /** Every apply, in order. */
  applied: [] as { kind: string; target_id: string; action: string }[],
};

export function resetFakeImpact() {
  fakeImpact.previews = new Map();
  fakeImpact.applied = [];
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

const line = (code: string, params: Line["params"] = {}): Line => ({
  code,
  params,
  cost_usd: null,
  optional: false,
});

function episodeOfBlock(id: string) {
  const found = findBlock(id);
  return fakeEpisodes.list.find((e) => e.id === found?.script.episode_id);
}

/** What the change touches that is confirmed, or null when the kind is not faked. */
function linesOf(kind: string, target: string): Line[] | null {
  if (kind === "line_edit" || kind === "scene_edit") {
    const ep = episodeOfBlock(target);
    return ep?.script_status === "confirmed" ? [line("self_script", { n: ep.idx })] : [];
  }
  return null;
}

/** Write the change (只改这里 and 确认并同步 both do); an error answer, or null once written. */
function write(kind: string, target: string, patch: Record<string, unknown>): Response | null {
  const text = typeof patch.text === "string" ? patch.text : undefined;
  const r = kind === "line_edit" ? editLine(target, text) : editScene(target, text);
  return "script" in r ? null : error(r.status, r.code);
}

/** The fake backend's `/impact/*` (the MSW demo relays them, `mocks/handlers/impact.ts`). */
export async function impactBackendFetch(request: Request): Promise<Response | null> {
  const { pathname } = new URL(request.url);
  if (pathname.endsWith("/impact/preview")) {
    const change = ImpactChangeSchema.safeParse(await request.json());
    if (!change.success) return error(422, "invalid_request");
    const lines = linesOf(change.data.kind, change.data.target_id);
    if (!lines) return error(422, "unknown_change_kind", { kind: change.data.kind });
    const impact: Impact = {
      id: `imp-${fakeImpact.previews.size + 1}`,
      change: change.data,
      lines,
      unaffected: null,
      rerun_cost_usd: 0,
      stale: {},
    };
    fakeImpact.previews.set(impact.id, impact);
    return HttpResponse.json(impact);
  }
  if (pathname.endsWith("/impact/apply")) {
    const body = ApplyImpactRequestSchema.safeParse(await request.json());
    if (!body.success) return error(422, "invalid_request");
    const { impact_id: id, action } = body.data;
    const impact = fakeImpact.previews.get(id);
    if (!impact) return error(404, "impact_not_found", { id });
    fakeImpact.previews.delete(id);
    const { kind, target_id, patch } = impact.change;
    fakeImpact.applied.push({ kind, target_id, action });
    if (action !== "undo") {
      const failed = write(kind, target_id, patch);
      if (failed) return failed;
    }
    const jobs = action === "rerun" && impact.lines.length ? ["job-sync-1"] : [];
    return HttpResponse.json({ action, stale: impact.stale, job_ids: jobs });
  }
  return null;
}

/** `POST /gates/novel|script/confirm|reopen`; the later gates fall through to the MSW demo. */
export function gateHandlers() {
  return [
    http.post("*/api/v1/gates/:gate/:action", async ({ params, request }) => {
      const gate = String(params.gate);
      const action = String(params.action);
      if (gate !== "novel" && gate !== "script") return undefined;
      const { scope_id: scope } = (await request.json()) as { scope_id: string };
      const ep = fakeEpisodes.list.find((e) => e.id === scope);
      if (!ep && gate === "script") return error(404, "episode_not_found", { id: scope });
      const state = action === "confirm" ? "confirmed" : "in_progress";
      if (gate === "novel") {
        for (const p of Object.values(fakeEpisodes.progress))
          p.steps.novel = { ...p.steps.novel, state };
      } else if (ep) {
        const step = fakeEpisodes.progress[ep.id]?.steps.script;
        if (step) step.state = state;
        if (ep.script_status !== "none")
          ep.script_status = action === "confirm" ? "confirmed" : "draft";
      }
      return HttpResponse.json({
        id: `gate-${gate}-${action}`,
        gate,
        scope_id: gate === "novel" ? (ep?.series_id ?? scope) : scope,
        action,
        decided_at: "2026-10-20T10:00:00Z",
      });
    }),
  ];
}

/** The novel gate reopened (as 「重新打开」 leaves it): the novel step's products unlocked. */
export function reopenFakeNovel() {
  for (const p of fakeBible.products)
    if (p.locked_hash) Object.assign(p, { locked_hash: null, status: "adopted" });
  for (const p of Object.values(fakeEpisodes.progress))
    p.steps.novel = { ...p.steps.novel, state: "in_progress" };
}
