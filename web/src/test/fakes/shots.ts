/**
 * Fake 分镜 for page tests: episode 1's nine shots, its 分镜规划 and the seven keyframe products
 * as the Mock backend answers them (`test/data/shots.json`, written by
 * tests/api/test_web_fixtures.py), following the backend's rules (`shots/service.py`) as far as
 * the pages need them:
 * - 改设定 (`PATCH /shots/{id}`): written in place (the plan's edit versions are not kept);
 *   refused on a confirmed shot (409 `shot_confirmed`) and on a confirmed storyboard (409
 *   `product_locked`); shorter than its audio: 422 `duration_below_audio`; the duration follows
 *   `timing.shot_duration` (null: back to automatic);
 * - 拆分 / 和下一个合并 (`shots/ops.py`): lines halved (or cut after a line) / joined, shots
 *   renumbered; the new half gets an empty keyframe product, the merged one's goes;
 * - 选这个: the keyframe product's pick in the version on screen (409 `nothing_to_pick`);
 * - 确认这个镜头: the picked draft candidate becomes an adopted, locked `pick` version (a final's
 *   lone picture is locked as it is; the version on screen stays); a continuous shot needs none.
 *   Taking it back unlocks the keyframe and reopens 分镜确认;
 * - keyframe runs: 重跑 three local drafts; 「用 API 出终版」 one picture whose parent is the draft;
 * - 换来源 (M5.5, `shots/upload.py`, `POST /versions/{id}/redraw|inpaint|upscale`): an upload is
 *   one picked candidate at the delivery size (`low_res` under the draft size); 重画 / 局部修复 /
 *   放大 one candidate whose parent is that version (放大: at the delivery size, `stage=final`);
 *   continuous shots 409 `no_keyframe`, a locked keyframe 409 `product_locked`;
 * - 分镜确认 needs every shot confirmed and none 「待更新」 (409 `shots_not_confirmed`); it locks
 *   the plan;
 * - the impact preview's `shot_edit` (a confirmed shot, a confirmed storyboard) and
 *   `spec_aspect` (`test/fakes/impact.ts`).
 */
import { http, HttpResponse } from "msw";
import { z } from "zod";

import { injectEvent } from "@/api/events";
import type { Impact } from "@/api/schemas/impact";
import type { Job } from "@/api/schemas/jobs";
import {
  ProductSchema,
  type Product,
  type ProductVersion,
  type RunRequest,
} from "@/api/schemas/products";
import {
  ShotChecksSchema,
  ShotPatchSchema,
  ShotSchema,
  type Shot,
  type ShotIssue,
  type ShotPatch,
} from "@/api/schemas/shots";
import { primaryModel } from "@/mocks/route";
import data from "@/test/data/shots.json";
import { fakeResolve } from "@/test/fakes/config";

const demoShots = z.array(ShotSchema).parse(data.shots);
const demoPlan = ProductSchema.parse(data.plan);
const demoKeyframes = data.keyframes.map((p) => ProductSchema.parse(p));
const demoChecks = ShotChecksSchema.parse(data.checks);
/** What the Mock model's 分镜检查 finds in episode 1 (`pipeline/components/plancheck.py`). */
const MOCK_LLM_ISSUE: ShotIssue = {
  shot_id: "demo-shot-1-03",
  label: "1-03",
  code: "insert_event",
  params: {},
  source: "llm",
  text: "插入镜头写了「雨水把字一点点泡开」：状态变化应该摆好，不要在镜头里发生。",
};

/** The episode the fixture's shots are of. */
const EPISODE = "demo-e1";
/** 「用 API 出终版」 of one keyframe (Nano Banana 2.1, one picture: `RunService.final_cost`). */
export const FINAL_COST = 0.0504;

/** State of the fake; `resetFakeShots()` (called by `backend()`) restores it. */
export const fakeShots = {
  shots: structuredClone(demoShots),
  plan: structuredClone(demoPlan),
  keyframes: structuredClone(demoKeyframes),
  /** 分镜检查 (M5.5): the rules' findings; `POST` adds the Mock model's. */
  checks: structuredClone(demoChecks),
  /** Episodes whose 分镜确认 is confirmed. */
  confirmed: new Set<string>(),
  /** Every `PATCH /shots/{id}`, in order. */
  patches: [] as ({ id: string } & ShotPatch)[],
  /** Every 换来源 request (M5.5), in order. */
  edits: [] as PictureEdit[],
};

/** What a 换来源 request sent. */
export type PictureEdit =
  | { kind: "upload"; shot: string; name: string; box: Record<string, number> | null }
  | { kind: "redraw"; version: string; body: Record<string, unknown> }
  | {
      kind: "inpaint";
      version: string;
      idx: number;
      prompt: string | null;
      where: string | null;
      mask: number;
    }
  | { kind: "upscale"; version: string; idx: number };

/** The delivery size of the fixture's 9:16 spec, and its draft tier (`spec/dims.py`). */
const DELIVERY = { w: 1080, h: 1920 };
const DRAFT = { w: 768, h: 1366 };

export function resetFakeShots() {
  fakeShots.shots = structuredClone(demoShots);
  fakeShots.plan = structuredClone(demoPlan);
  fakeShots.keyframes = structuredClone(demoKeyframes);
  fakeShots.checks = structuredClone(demoChecks);
  fakeShots.confirmed = new Set();
  fakeShots.patches = [];
  fakeShots.edits = [];
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

export const findShot = (id: unknown) => fakeShots.shots.find((s) => s.id === id);
const keyframeOf = (s: Shot) => fakeShots.keyframes.find((p) => p.id === s.keyframe_product_id);
const productById = (id: unknown) =>
  [fakeShots.plan, ...fakeShots.keyframes].find((p) => p.id === id);
const current = (p: Product) => p.versions.find((v) => v.id === p.current_version_id);

/** `keyframe_sha256`: the picked candidate's picture in the keyframe's version on screen. */
function repicture(s: Shot) {
  const kf = keyframeOf(s);
  const v = kf && current(kf);
  s.keyframe_sha256 =
    v?.files.find((f) => f.role === "candidate" && (f.idx ?? 0) === s.keyframe_pick)?.sha256 ??
    null;
}

function announce(p: Product) {
  setTimeout(() =>
    injectEvent("product.updated", { product_id: p.id, series_id: p.series_id, status: p.status }),
  );
}

/** 分镜 n / m of episode 1 (`ShotService.badge`), or null for another episode. */
export function fakeShotsBadge(episodeId: string) {
  if (episodeId !== EPISODE) return null;
  const list = fakeShots.shots;
  return {
    state: fakeShots.confirmed.has(episodeId) ? ("confirmed" as const) : ("in_progress" as const),
    done: list.filter((s) => s.confirmed).length,
    total: list.length,
    stale: list.filter((s) => s.confirm_stale).length,
  };
}

function reopenGate() {
  if (!fakeShots.confirmed.delete(EPISODE)) return;
  Object.assign(fakeShots.plan, { locked_hash: null, status: "adopted" });
}

/** 分镜确认 / 重新打开 (scope: the episode); the refusal, or null. */
export function fakeStoryboardGate(episodeId: string, action: string): Response | null {
  if (episodeId !== EPISODE) return error(404, "episode_not_found", { id: episodeId });
  if (action !== "confirm") {
    reopenGate();
    return null;
  }
  const waiting = fakeShots.shots.filter((s) => !s.confirmed || s.confirm_stale);
  if (waiting.length)
    return error(409, "shots_not_confirmed", {
      gate: "storyboard",
      scope_id: episodeId,
      count: waiting.length,
      labels: waiting.map((s) => s.label).join("、"),
    });
  fakeShots.confirmed.add(episodeId);
  const v = current(fakeShots.plan);
  Object.assign(fakeShots.plan, {
    locked_hash: v?.content_hash ?? "sha256:plan",
    status: "locked",
  });
  return null;
}

function unconfirm(s: Shot) {
  if (!s.confirmed) return;
  s.confirmed = false;
  s.confirm_stale = false;
  const kf = keyframeOf(s);
  if (kf?.locked_hash) {
    Object.assign(kf, { locked_hash: null, status: "adopted" });
    announce(kf);
  }
  reopenGate();
}

/** 确认这个镜头: the refusal, or null once confirmed. */
function confirm(s: Shot): Response | null {
  if (s.shot_type !== "continuous") {
    const kf = keyframeOf(s);
    const source = kf && current(kf);
    if (!kf || !source) return error(409, "nothing_to_confirm", { id: s.id });
    if (kf.locked_hash) return error(409, "product_locked", { id: kf.id });
    const many = source.files.filter((f) => f.role === "candidate").length > 1;
    let locked = source;
    if (many) {
      const file = source.files.find((f) => f.role === "candidate" && f.idx === s.keyframe_pick);
      locked = addVersion(kf, 0, { origin: "pick", model: source.model_key, stage: source.stage });
      locked.parent_version_id = source.id;
      locked.files = file ? [{ ...file, role: "ref", idx: null }] : [];
      kf.current_version_id = source.id; // the version on screen stays
    }
    Object.assign(kf, {
      adopted_version_id: locked.id,
      locked_hash: locked.content_hash,
      status: "locked",
      pick: { version_id: source.id, idx: s.keyframe_pick },
    });
    announce(kf);
  }
  s.confirmed = true;
  s.confirm_stale = false;
  return null;
}

/** `timing.shot_duration`: dialogue runs as long as its audio unless made longer by hand; the
 * rest by hand, else the plan's seconds; never shorter than what is spoken (`min_s`). */
function retime(s: Shot) {
  const dialogue = s.dialogue !== null && !s.dialogue.includes("画外音");
  const base = s.manual_s ?? (dialogue ? s.min_s : (s.planned_s ?? 3));
  s.duration_source = (dialogue && s.manual_s === null) || s.min_s > base ? "audio" : "manual";
  s.duration_s = Math.max(base, s.min_s);
  s.split_hint = s.longest_s !== null && s.duration_s > s.longest_s;
}

/** The settings of `PATCH /shots/{id}` written in place (no checks); the refusal, or null. */
function write(s: Shot, patch: ShotPatch): Response | null {
  const { confirmed, keyframe_pick: pick, intent, duration_s: seconds, contract, ...rest } = patch;
  void confirmed;
  if (contract) {
    // 镜头契约 (M5.5): only the fields given; ``delivery`` only the lines given.
    const delivery = { ...s.contract.delivery, ...contract.delivery };
    s.contract = { ...s.contract, ...contract, delivery };
    if (contract.kind === "insert") s.contract.beats = 0;
  }
  if (seconds !== undefined) {
    if (seconds !== null && seconds < s.min_s)
      return error(422, "duration_below_audio", { id: s.id, min_s: s.min_s });
    s.manual_s = seconds;
    retime(s);
  }
  Object.assign(s, rest);
  const kf = keyframeOf(s);
  if (intent !== undefined) {
    s.intent = intent;
    if (kf)
      kf.prompt = {
        intent,
        compiled: `[画面] ${intent}`,
        compiled_overridden: false,
        model_key: kf.prompt?.model_key ?? "comfy/qwen-image-edit",
      };
  }
  if (pick !== undefined) {
    if (!kf?.current_version_id) return error(409, "nothing_to_pick", { id: s.id });
    s.keyframe_pick = pick;
    kf.pick = { version_id: kf.current_version_id, idx: pick };
    repicture(s);
  }
  return null;
}

function patchShot(s: Shot, patch: ShotPatch): Response {
  fakeShots.patches.push({ id: s.id, ...patch });
  const fields = Object.keys(patch).filter((k) => k !== "confirmed");
  if (patch.confirmed === false) unconfirm(s);
  else if (fields.length && s.confirmed) return error(409, "shot_confirmed", { id: s.id });
  const planFields = fields.filter((k) => k !== "intent" && k !== "keyframe_pick");
  if (planFields.length && fakeShots.plan.locked_hash)
    return error(409, "product_locked", { id: fakeShots.plan.id });
  const refused = write(s, patch) ?? (patch.confirmed ? confirm(s) : null);
  return refused ?? HttpResponse.json(s);
}

// ------------------------------------------------------------------ the impact preview

type Line = Impact["lines"][number];
const line = (code: string, params: Line["params"], cost: number | null = null): Line => ({
  code,
  params,
  cost_usd: cost,
  optional: false,
});

/** `shot_edit` (`ShotService.plan_edit`): the confirmation it takes back, a new picture
 * description's redraw, 分镜确认 reopened. Null for an unknown shot. */
export function shotEditImpact(shotId: string, patch: Record<string, unknown>): Line[] | null {
  const s = findShot(shotId);
  if (!s) return null;
  const lines: Line[] = [];
  const next = patch.merge ? nextInScene(s) : undefined;
  const confirmed = [s, ...(next ? [next] : [])].filter((x) => x.confirmed);
  if (confirmed.length)
    lines.push(
      line("shot_reconfirm", {
        shots: confirmed.map((x) => x.label).join("、"),
        count: confirmed.length,
      }),
    );
  if (patch.intent !== undefined && keyframeOf(s))
    lines.push(line("shot_redraw", { shot: s.label }));
  if (fakeShots.confirmed.has(s.episode_id)) lines.push(line("gate_storyboard", { n: 1 }));
  return lines;
}

/** Applying `shot_edit`: 分镜确认 reopened, the shot's confirmation taken back (and the next
 * one's, merging), the edit written; 确认并同步 also draws its keyframe again. */
export function editFakeShot(shotId: string, patch: Record<string, unknown>, redraw: boolean) {
  const s = findShot(shotId);
  if (!s) return;
  reopenGate();
  unconfirm(s);
  const split = patch.split as { after_line_id?: string | null } | undefined;
  if (split) splitShot(s, split.after_line_id ?? null);
  else if (patch.merge) {
    const next = nextInScene(s);
    if (next) unconfirm(next);
    mergeShot(s);
  } else write(s, ShotPatchSchema.parse(patch));
  const kf = keyframeOf(s);
  if (redraw && kf) run(kf, { mode: "run", where: "local" });
}

/** Changing or unlocking a locked asset (`ShotService._asset_shots`): the shots that use it,
 * and which of those with a keyframe are confirmed. */
export function assetShotLines(assetId: string): Line[] {
  const using = fakeShots.shots.filter((s) => s.asset_ids.includes(assetId));
  if (!using.length) return [];
  const lines = [
    line("shot_refs", { ids: using.map((s) => s.label).join("、"), count: using.length }),
  ];
  const drawn = using.filter((s) => s.confirmed && s.shot_type !== "continuous");
  if (drawn.length)
    lines.push(
      line("shots_confirmed_redraw", {
        shots: drawn.map((s) => s.label).join("、"),
        count: drawn.length,
      }),
    );
  return lines;
}

/** `spec_aspect` (`ShotService.plan_aspect`) from 9:16: the keyframes drawn so far at their
 * finals' price. Scene pictures are drawn 16:9 whatever the spec, so none to redraw. */
export function specAspectImpact(): Line[] {
  const drawn = fakeShots.keyframes.filter((p) => p.current_version_id);
  const cost = Math.round(drawn.length * FINAL_COST * 100) / 100;
  return drawn.length
    ? [line("keyframes_redraw", { count: drawn.length, shots: fakeShots.shots.length }, cost)]
    : [];
}

/** Applying `spec_aspect` (the spec itself is written by the caller): every confirmation taken
 * back; 确认并同步 also draws the keyframes again as local drafts. */
export function aspectFakeShots(redraw: boolean) {
  for (const s of fakeShots.shots) unconfirm(s);
  if (redraw) for (const kf of fakeShots.keyframes) run(kf, { mode: "run", where: "local" });
}

// ------------------------------------------------------------------ split, merge

function renumber() {
  fakeShots.shots.forEach((s, i) => {
    s.idx = i + 1;
    s.label = `1-${String(i + 1).padStart(2, "0")}`;
  });
}

const nextInScene = (s: Shot) => {
  const next = fakeShots.shots[fakeShots.shots.indexOf(s) + 1];
  return next?.scene_id === s.scene_id ? next : undefined;
};

let made = 0;

/** 拆分 (`ops.split`): the lines halved, or cut after `after`; one action line is filmed by
 * both, one spoken line stays in the first (the second is a 2 s reaction). The refusal, or null. */
function splitShot(s: Shot, after: string | null): Response | null {
  const lines = s.line_ids;
  if (after !== null && !lines.slice(0, -1).includes(after))
    return error(422, "split_point_invalid", { id: after });
  const cut = after !== null ? lines.indexOf(after) + 1 : Math.ceil(lines.length / 2);
  const one = lines.length === 1;
  const head = one ? lines : lines.slice(0, cut);
  const tail = one ? (s.dialogue ? [] : [...lines]) : lines.slice(cut);
  const id = `shot-new-${++made}`;
  const kf: Product = {
    ...structuredClone(fakeShots.keyframes[0] as Product),
    id: `p-kf-${id}`,
    owner_id: id,
    current_version_id: null,
    adopted_version_id: null,
    locked_hash: null,
    status: "empty",
    versions: [],
    pick: null,
    prompt: null,
  };
  fakeShots.keyframes.push(kf);
  const half = tail.length ? Math.max(1, Math.round(((s.planned_s ?? 4) / 2) * 10) / 10) : 2;
  const second: Shot = {
    ...structuredClone(s),
    id,
    line_ids: tail,
    shot_type: "same_scene_cut",
    tail_from: null,
    tail_note: null,
    dialogue: tail.length ? s.dialogue : null,
    min_s: tail.length ? s.min_s : 0,
    planned_s: half,
    manual_s: null,
    keyframe_product_id: kf.id,
    keyframe_pick: 0,
    keyframe_sha256: null,
    confirmed: false,
    confirm_stale: false,
  };
  Object.assign(s, { line_ids: head, planned_s: tail.length ? half : s.planned_s, manual_s: null });
  retime(s);
  retime(second);
  for (const x of fakeShots.shots) if (x.tail_from === s.label) x.tail_from = "pending";
  fakeShots.shots.splice(fakeShots.shots.indexOf(s) + 1, 0, second);
  renumber();
  for (const x of fakeShots.shots) if (x.tail_from === "pending") x.tail_from = second.label;
  return null;
}

/** 和下一个合并 (`ops.merge`): the next shot of the scene folds into this one; its keyframe goes. */
function mergeShot(s: Shot): Response | null {
  const next = nextInScene(s);
  if (!next) return error(422, "no_next_shot", { id: s.id });
  s.line_ids = [...new Set([...s.line_ids, ...next.line_ids])];
  s.asset_ids = [...new Set([...s.asset_ids, ...next.asset_ids])];
  s.planned_s = (s.planned_s ?? 0) + (next.planned_s ?? 0) || null;
  s.min_s = s.min_s + next.min_s;
  s.manual_s = null;
  retime(s);
  fakeShots.keyframes = fakeShots.keyframes.filter((p) => p.id !== next.keyframe_product_id);
  fakeShots.shots.splice(fakeShots.shots.indexOf(next), 1);
  renumber();
  return null;
}

/** 拆分 / 合并 by the plain endpoints: refused on a confirmed shot (and the next one, merging). */
function splitOrMerge(s: Shot, run: () => Response | null, others: Shot[] = []): Response {
  for (const x of [s, ...others])
    if (x.confirmed) return error(409, "shot_confirmed", { id: x.id });
  if (fakeShots.plan.locked_hash) return error(409, "product_locked", { id: fakeShots.plan.id });
  return run() ?? HttpResponse.json(fakeShots.shots);
}

// ------------------------------------------------------------------ keyframe runs

function addVersion(
  p: Product,
  count: number,
  v: { origin: ProductVersion["origin"]; model: string | null; stage: ProductVersion["stage"] },
): ProductVersion {
  const n = p.versions.length + 1;
  const id = `${p.id}-v${n}`;
  const version: ProductVersion = {
    id,
    product_id: p.id,
    n,
    origin: v.origin,
    parent_version_id: p.current_version_id,
    payload: { candidates: Array.from({ length: count }, () => ({})), aspect: "9:16", refs: [] },
    files: Array.from({ length: count }, (_, i) => ({
      role: "candidate",
      path: `blobs/sha256/00/${id}-${i}`,
      sha256: `${id}-${i}`,
      mime: "image/png",
      duration_s: null,
      w: 768,
      h: 1366,
      idx: i,
    })),
    content_hash: `sha256:${id}`,
    intent: p.prompt?.intent ?? current(p)?.intent ?? "",
    compiled: p.prompt?.compiled ?? "",
    compiled_overridden: false,
    model_key: v.model,
    where: v.model ? (v.model.startsWith("comfy/") ? "local" : "api") : null,
    seed: n,
    params: {},
    qa: null,
    qa_pass: null,
    fallback_reason: null,
    stage: v.stage,
    rating: null,
    cost_usd: v.stage === "final" ? FINAL_COST : 0,
    job_id: `job-${id}`,
    created_at: "2026-10-22T10:00:00Z",
    note: null,
  };
  p.versions.push(version);
  p.current_version_id = id;
  if (!p.locked_hash) p.status = "ready";
  announce(p);
  return version;
}

function job(p: Product, id: string, model: string, mode: string): Job {
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
    est_cost_usd: 0,
    fallback_from_job_id: null,
    created_at: "2026-10-22T10:00:00Z",
    started_at: "2026-10-22T10:00:00Z",
    finished_at: "2026-10-22T10:00:01Z",
  };
}

/** 重跑: three local drafts; 「用 API 出终版」 (`where: api` with the draft as
 * `params.source_version_id`): one picture on the API model, its parent the draft. A new
 * version on screen moves the pick back to its first picture. */
function run(p: Product, body: RunRequest): Job {
  const route = fakeResolve(p.component_id, null)?.values ?? null;
  const source = body.where === "api" ? body.params?.source_version_id : undefined;
  const model = source
    ? (route?.api_model ?? "google/nano-banana-pro")
    : (primaryModel(route) ?? "comfy/qwen-image-edit");
  const v = addVersion(p, source ? 1 : 3, {
    origin: body.mode,
    model,
    stage: source ? "final" : model.startsWith("comfy/") ? "draft" : null,
  });
  if (typeof source === "string") v.parent_version_id = source;
  const s = fakeShots.shots.find((x) => x.keyframe_product_id === p.id);
  if (s) {
    if (!s.confirmed) s.keyframe_pick = 0;
    repicture(s);
  }
  return job(p, v.id, model, body.mode);
}

// ------------------------------------------------------------------ endpoints

/** The fake backend's answers the MSW demo reads (`mocks/backend.ts`): the shots the post demo
 * lays out, and a shot's or the episode's products. */
export function shotsBackendFetch(url: URL): Response | null {
  const m = /\/episodes\/([^/]+)\/shots$/.exec(url.pathname);
  if (m) {
    const id = decodeURIComponent(m[1] ?? "");
    return HttpResponse.json(id === EPISODE ? fakeShots.shots : []);
  }
  return null;
}

/** The plan and keyframe products of an owner (`episode:<id>`, `shot:<id>`). */
export function fakeShotProducts(owner: string): Product[] {
  const [kind, id] = owner.split(":");
  if (kind === "episode") return fakeShots.plan.owner_id === id ? [fakeShots.plan] : [];
  if (kind === "shot") return fakeShots.keyframes.filter((p) => p.owner_id === id);
  return [];
}

export function shotHandlers() {
  return [
    http.get("*/api/v1/episodes/:id/shots", ({ params }) =>
      HttpResponse.json(params.id === EPISODE ? fakeShots.shots : []),
    ),

    http.get("*/api/v1/episodes/:id/shot-checks", ({ params }) =>
      params.id === EPISODE
        ? HttpResponse.json(fakeShots.checks)
        : HttpResponse.json({ issues: [], llm_product_id: null, llm_state: "none" }),
    ),

    http.post("*/api/v1/episodes/:id/shot-checks", ({ params }) => {
      if (params.id !== EPISODE) return error(404, "episode_not_found", { id: params.id });
      const rules = fakeShots.checks.issues.filter((i) => i.source === "rule");
      const issues = [...rules, MOCK_LLM_ISSUE].sort((a, b) => a.label.localeCompare(b.label));
      fakeShots.checks = { ...fakeShots.checks, issues, llm_state: "ready" };
      return HttpResponse.json(job(fakeShots.plan, "shot-check", "deepseek/v4.1-flash", "run"));
    }),

    http.patch("*/api/v1/shots/:id", async ({ params, request }) => {
      const s = findShot(params.id);
      if (!s) return error(404, "shot_not_found", { id: params.id });
      const body = ShotPatchSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      return patchShot(s, body.data);
    }),

    http.post("*/api/v1/shots/:id/split", async ({ params, request }) => {
      const s = findShot(params.id);
      if (!s) return error(404, "shot_not_found", { id: params.id });
      const body = (await request.json()) as { after_line_id?: string | null };
      return splitOrMerge(s, () => splitShot(s, body.after_line_id ?? null));
    }),

    http.post("*/api/v1/shots/:id/merge", ({ params }) => {
      const s = findShot(params.id);
      if (!s) return error(404, "shot_not_found", { id: params.id });
      const next = nextInScene(s);
      return splitOrMerge(s, () => mergeShot(s), next ? [next] : []);
    }),

    http.get("*/api/v1/products/:id", ({ params }) => {
      const p = productById(params.id);
      return p ? HttpResponse.json(p) : undefined;
    }),

    http.post("*/api/v1/shots/:id/keyframe/upload", async ({ params, request }) => {
      const s = findShot(params.id);
      if (!s) return error(404, "shot_not_found", { id: params.id });
      const kf = keyframeOf(s);
      if (s.shot_type === "continuous" || !kf) return error(409, "no_keyframe", { id: s.id });
      if (kf.locked_hash) return error(409, "product_locked", { id: kf.id });
      const form = await request.formData();
      const file = form.get("file");
      const name = typeof file === "object" && file && "name" in file ? String(file.name) : "";
      const nums = ["x", "y", "w", "h"].map((k) => form.get(k));
      const box = nums.every((v) => v !== null)
        ? { x: Number(nums[0]), y: Number(nums[1]), w: Number(nums[2]), h: Number(nums[3]) }
        : null;
      fakeShots.edits.push({ kind: "upload", shot: s.id, name, box });
      const v = addVersion(kf, 1, { origin: "upload", model: null, stage: null });
      v.note = name || null;
      v.payload = {
        candidates: [{}],
        crop: box,
        ...(box && (box.w < DRAFT.w || box.h < DRAFT.h) ? { low_res: true } : {}),
      };
      for (const f of v.files) Object.assign(f, DELIVERY);
      kf.pick = { version_id: v.id, idx: 0 };
      s.keyframe_pick = 0;
      repicture(s);
      return HttpResponse.json(kf);
    }),

    http.post("*/api/v1/versions/:id/:op", async ({ params, request }) => {
      const op = String(params.op);
      if (op !== "redraw" && op !== "inpaint" && op !== "upscale") return undefined;
      const id = String(params.id);
      const kf = fakeShots.keyframes.find((p) => p.versions.some((v) => v.id === id));
      if (!kf) return undefined;
      if (kf.locked_hash) return error(409, "product_locked", { id: kf.id });
      let where: string | null;
      if (op === "inpaint") {
        const form = await request.formData();
        const mask = form.get("mask");
        const prompt = form.get("prompt");
        const w = form.get("where");
        where = typeof w === "string" ? w : null;
        fakeShots.edits.push({
          kind: "inpaint",
          version: id,
          idx: Number(form.get("idx") ?? 0),
          prompt: typeof prompt === "string" ? prompt : null,
          where,
          mask: typeof mask === "object" && mask ? mask.size : 0,
        });
      } else {
        const body = (await request.json()) as Record<string, unknown>;
        where = typeof body.where === "string" ? body.where : null;
        fakeShots.edits.push(
          op === "redraw"
            ? { kind: "redraw", version: id, body }
            : { kind: "upscale", version: id, idx: Number(body.idx ?? 0) },
        );
      }
      const model = {
        redraw: where === "api" ? "google/nano-banana-2.1" : "comfy/flux3-klein-redraw",
        inpaint: where === "api" ? "openai/gpt-image-2" : "comfy/klein-inpaint",
        upscale: "comfy/seedvr2-img",
      }[op];
      const v = addVersion(kf, 1, {
        origin: op,
        model,
        stage: op === "upscale" ? "final" : model.startsWith("comfy/") ? "draft" : null,
      });
      v.parent_version_id = id;
      if (op === "upscale") for (const f of v.files) Object.assign(f, DELIVERY);
      const s = fakeShots.shots.find((x) => x.keyframe_product_id === kf.id);
      if (s) {
        s.keyframe_pick = 0;
        repicture(s);
      }
      return HttpResponse.json(job(kf, v.id, model, op));
    }),

    http.post("*/api/v1/products/:id/run", async ({ params, request }) => {
      const p = fakeShots.keyframes.find((x) => x.id === params.id);
      if (!p) return undefined;
      return HttpResponse.json(run(p, (await request.json()) as RunRequest));
    }),
  ];
}
