/**
 * Fake gates (小说, 剧本) and impact previews for page tests, following the backend's rules
 * (`pipeline/gates.py`, `pipeline/impact.py`) as far as the pages need them: confirming flips
 * the step badges and the script status; a preview of an edit to confirmed work lists
 * 「已确认的 … 会改成新内容」 and what reads it, and 只改这里 / 确认并同步 write the edit through
 * the request a direct edit sends (the sync's reruns are the backend's; here they only show up
 * as job ids).
 */
import { http, HttpResponse } from "msw";

import { ApplyImpactRequestSchema, ImpactChangeSchema, type Impact } from "@/api/schemas/impact";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import { fakeBible } from "@/test/fakes/bible";
import { fakeEpisodes } from "@/test/fakes/episodes";
import { fakeScript, findBlock } from "@/test/fakes/script";

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

const line = (code: string, params: Line["params"] = {}, cost: number | null = null): Line => ({
  code,
  params,
  cost_usd: cost,
  optional: code.startsWith("then_"),
});

/** The novel step's kinds and the slot of the product they change. */
const NOVEL_SLOT: Record<string, string> = {
  novel_edit: "novel",
  novel_replace: "novel",
  bible_edit: "bible",
  bible_merge: "bible",
  suggestion_decision: "suggestions",
};

/**
 * A change on the novel step: 「已确认的 …」 when the novel is confirmed, what reads it (补全 →
 * 设定 → 分集 → the confirmed scripts) and the gates that reopen. Nothing when neither the novel
 * nor a script is confirmed (the page writes those directly).
 */
function novelLines(slot: string): Line[] {
  const novel = Object.values(fakeEpisodes.progress).some(
    (p) => p.steps.novel.state === "confirmed",
  );
  const scripts = fakeEpisodes.list.filter((e) => e.script_status === "confirmed");
  if (!novel && !scripts.length) return [];
  const lines = novel ? [line(`self_${slot}`)] : [];
  if (slot === "novel") lines.push(line("stale_suggestions", {}, 0.02), line("stale_bible"));
  if (slot === "suggestions") lines.push(line("stale_bible"));
  lines.push(line(slot === "bible" ? "stale_episodes" : "then_episodes", {}, 0.01));
  for (const e of scripts) lines.push(line("then_script", { n: e.idx }, 0.03));
  if (novel) lines.push(line("gate_novel"));
  for (const e of scripts) lines.push(line("gate_script", { n: e.idx }));
  return lines;
}

/** A beat moved or edited: the confirmed scripts of the episodes it leaves and joins. */
function beatLines(id: string, patch: Record<string, unknown>): Line[] {
  const from = fakeEpisodes.list.find((e) => e.beats.some((b) => b.id === id));
  const to = fakeEpisodes.list.find((e) => e.id === patch.episode_id);
  return [...new Set([from, to])]
    .filter((e) => e?.script_status === "confirmed")
    .flatMap((e) =>
      e ? [line("stale_script", { n: e.idx }, 0.05), line("gate_script", { n: e.idx })] : [],
    );
}

/** What the change reaches, or null when the kind is not faked. */
function linesOf(kind: string, target: string, patch: Record<string, unknown>): Line[] | null {
  if (kind === "line_edit" || kind === "scene_edit") {
    const found = findBlock(target);
    const ep = fakeEpisodes.list.find((e) => e.id === found?.script.episode_id);
    return ep?.script_status === "confirmed" ? [line("self_script", { n: ep.idx })] : [];
  }
  const slot = NOVEL_SLOT[kind];
  if (slot) return novelLines(slot);
  if (kind === "beat_move") return beatLines(target, patch);
  return null;
}

/** The direct request that writes the same change (the fake's own handlers take it). */
function direct(kind: string, id: string, p: Record<string, unknown>) {
  const enc = encodeURIComponent;
  switch (kind) {
    case "line_edit":
      return { method: "PATCH", path: `/lines/${enc(id)}`, body: { text: p.text } };
    case "scene_edit":
      return {
        method: "PATCH",
        path: `/scenes/${enc(id)}`,
        body: { heading: p.heading ?? p.text },
      };
    case "novel_edit":
      return {
        method: "PUT",
        path: `/series/${enc(id)}/novel/chapters/${String(p.chapter)}`,
        body: { title: p.title, paragraphs: p.paragraphs },
      };
    case "bible_edit":
      return { method: "PATCH", path: `/bible/${enc(id)}`, body: p };
    case "bible_merge":
      return { method: "POST", path: "/bible/merge", body: { ids: [id], ...p } };
    case "suggestion_decision":
      return { method: "POST", path: `/suggestions/${enc(id)}/${String(p.action)}`, body: {} };
    case "beat_move":
      return { method: "PATCH", path: `/beats/${enc(id)}`, body: p };
    default:
      return null; // novel_replace: the stored upload is the backend's; only recorded here
  }
}

/** Write the change (只改这里 and 确认并同步 both do); the error answer, or null once written. */
async function write(kind: string, target: string, patch: Record<string, unknown>) {
  const req = direct(kind, target, patch);
  if (!req) return null;
  const resp = await fetch(`${location.origin}/api/v1${req.path}`, {
    method: req.method,
    headers: { "Content-Type": "application/json", "X-Drama-Studio": "1" },
    body: JSON.stringify(req.body),
  });
  return resp.ok ? null : resp;
}

/** The fake backend's `/impact/*` (the MSW demo relays them, `mocks/handlers/impact.ts`). */
export async function impactBackendFetch(request: Request): Promise<Response | null> {
  const { pathname } = new URL(request.url);
  if (pathname.endsWith("/impact/preview")) {
    const change = ImpactChangeSchema.safeParse(await request.json());
    if (!change.success) return error(422, "invalid_request");
    const { kind, target_id, patch } = change.data;
    const lines = linesOf(kind, target_id, patch);
    if (!lines) return error(422, "unknown_change_kind", { kind });
    const cost = lines.reduce((sum, l) => sum + (l.cost_usd ?? 0), 0);
    const impact: Impact = {
      id: `imp-${fakeImpact.previews.size + fakeImpact.applied.length + 1}`,
      change: change.data,
      lines,
      unaffected: null,
      rerun_cost_usd: Math.round(cost * 100) / 100,
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
      const failed = await write(kind, target_id, patch);
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
      if (gate === "novel" && (ep || scope === DEMO_SERIES_ID)) {
        for (const p of Object.values(fakeEpisodes.progress))
          p.steps.novel = { ...p.steps.novel, state };
      } else if (gate === "novel") {
        fakeEpisodes.seriesNovel[scope] = state;
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

/** Every gate reopened: nothing confirmed, so pages write edits directly (no preview). */
export function openFakeGates() {
  reopenFakeNovel();
  for (const p of fakeScript.products)
    if (p.locked_hash) Object.assign(p, { locked_hash: null, status: "adopted" });
  for (const e of fakeEpisodes.list) {
    if (e.script_status === "confirmed") e.script_status = "draft";
    const step = fakeEpisodes.progress[e.id]?.steps.script;
    if (step?.state === "confirmed") step.state = "in_progress";
  }
}
