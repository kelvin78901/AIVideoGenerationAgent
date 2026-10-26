/**
 * Fake assets for page tests: episode 1's 13 assets, their products, 林晚's views and the
 * episode's 出场矩阵 as the Mock backend answers them (`test/data/assets.json`, written by
 * tests/api/test_web_fixtures.py), following the backend's rules (`assets/service.py`) as far
 * as the page needs them:
 * - 选这个 / 改描述 / 画面文字 / 音色来源 on the asset (refused once locked);
 * - 锁定为参考 turns the picked candidate of the version on screen into an adopted, locked
 *   `pick` version (the version on screen stays); on-screen text OCR read differently is
 *   refused (409 `ocr_mismatch`) unless `force`;
 * - 重跑 adds a version with fresh candidates (on-screen text: every one OCR-checked and
 *   matching; a voice: three auditions reading its lines); 「用 API 出终版」 one picture from
 *   the draft, or a voice's final (its sample and five emotions), which is locked whole while
 *   an audition cannot be (409 `voice_needs_final`);
 * - 上传参考图 adds a version with that one candidate, picked;
 * - 解锁 is the impact preview's `asset_unlock` (`test/fakes/impact.ts`): what uses the locked
 *   picture, then unlocked (and episode 1's assets gate reopened);
 * - editing a locked asset is the impact preview's `asset_edit`: saved, the lock kept; 确认并同步
 *   draws new candidates;
 * - episode 1's 素材 badge counts the assets it uses (those with scenes) and their locks, and
 *   its gate needs them all locked (409 `assets_not_locked`).
 */
import { http, HttpResponse } from "msw";

import { injectEvent } from "@/api/events";
import {
  AssetLockSchema,
  AssetMatrixSchema,
  AssetPatchSchema,
  AssetSchema,
  CandidatesPayloadSchema,
  type Asset,
  type AssetLock,
} from "@/api/schemas/assets";
import type { Impact } from "@/api/schemas/impact";
import type { Job } from "@/api/schemas/jobs";
import {
  ProductSchema,
  type Product,
  type ProductVersion,
  type RunRequest,
} from "@/api/schemas/products";
import { primaryModel } from "@/mocks/route";
import data from "@/test/data/assets.json";
import { fakeResolve } from "@/test/fakes/config";
import { assetShotLines } from "@/test/fakes/shots";

const demoAssets = data.assets.map((a) => AssetSchema.parse(a));
const demoProducts = data.products.map((p) => ProductSchema.parse(p));
const demoViews = data.views.map((p) => ProductSchema.parse(p));
const demoMatrix = AssetMatrixSchema.parse(data.matrix);

/** State of the fake; `resetFakeAssets()` (called by `backend()`) restores it. */
export const fakeAssets = {
  assets: structuredClone(demoAssets),
  products: structuredClone(demoProducts),
  /** 补视图 products (林晚's). */
  views: structuredClone(demoViews),
  /** Pictures uploaded, in order. */
  uploads: [] as { id: string; name: string }[],
  /** 重新分析剧本 requests, in order (episode ids). */
  analyses: [] as string[],
  /** Episodes whose assets gate is confirmed. */
  confirmed: new Set<string>(),
};

/** The episode the fixture's assets are about (their `scenes`). */
const EPISODE = "demo-e1";

export function resetFakeAssets() {
  fakeAssets.assets = structuredClone(demoAssets);
  fakeAssets.products = structuredClone(demoProducts);
  fakeAssets.views = structuredClone(demoViews);
  fakeAssets.uploads = [];
  fakeAssets.analyses = [];
  fakeAssets.confirmed = new Set();
}

const used = () => fakeAssets.assets.filter((a) => a.scenes.length > 0);

/** 素材 n / m of episode 1 (`AssetService.badge`), or null for another episode. */
export function fakeAssetsBadge(episodeId: string) {
  if (episodeId !== EPISODE) return null;
  const mine = used();
  const done = mine.filter((a) => productOf(a)?.locked_hash).length;
  const state = fakeAssets.confirmed.has(episodeId)
    ? ("confirmed" as const)
    : ("in_progress" as const);
  return { state, done, total: mine.length, stale: 0 };
}

/** `POST /gates/assets/confirm|reopen` (scope: the episode). */
export function fakeAssetsGate(episodeId: string, action: string): Response | null {
  if (episodeId !== EPISODE) return error(404, "episode_not_found", { id: episodeId });
  if (action === "confirm") {
    const open = used().filter((a) => !productOf(a)?.locked_hash);
    if (open.length)
      return error(409, "assets_not_locked", {
        gate: "assets",
        scope_id: episodeId,
        count: open.length,
        names: open.map((a) => a.name).join("、"),
      });
    fakeAssets.confirmed.add(episodeId);
  } else fakeAssets.confirmed.delete(episodeId);
  return null;
}

/** `asset_edit` of a locked asset (`AssetService.plan_edit`), or null when it is not locked. */
export function assetEditImpact(assetId: string): Pick<Impact, "lines" | "unaffected"> | null {
  const a = findAsset(assetId);
  const p = a && productOf(a);
  if (!a || !p?.locked_hash) return null;
  const line = (code: string, params: Record<string, string | number>, cost: number | null) => ({
    code,
    params,
    cost_usd: cost,
    optional: false,
  });
  const scenes = a.scenes.map((s) => s.number);
  return {
    lines: [
      line("asset_redraw", { name: a.name, kind: a.kind }, p.estimate?.cost_usd || null),
      ...(fakeAssets.views.some((v) => v.owner_id === a.id)
        ? [line("uses_ref_views", { name: a.name }, null)]
        : []),
      ...(scenes.length
        ? [line("asset_in_scenes", { scenes: scenes.join("、"), count: scenes.length }, null)]
        : []),
      ...assetShotLines(a.id),
    ],
    unaffected: { code: "edit_keeps_ref", params: { name: a.name } },
  };
}

/** Applying `asset_edit`: the edit saved (the lock kept); 确认并同步 also redraws. */
export function editFakeAsset(assetId: string, patch: Record<string, unknown>, redraw: boolean) {
  const a = findAsset(assetId);
  const p = a && productOf(a);
  if (!a || !p) return;
  const body = AssetPatchSchema.parse(patch);
  if (body.intent !== undefined) {
    a.intent = body.intent;
    p.prompt = {
      intent: body.intent,
      compiled: `[描述] ${body.intent}`,
      compiled_overridden: false,
      model_key: p.prompt?.model_key ?? "comfy/qwen-image",
    };
  }
  if (body.text && a.text) a.text = { ...a.text, ...body.text };
  if (body.voice && a.voice) a.voice = { ...a.voice, ...body.voice };
  if (redraw) run(p, { mode: "rerun" });
}

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

const productOf = (a: Asset) => fakeAssets.products.find((p) => p.id === a.product_id);
const findAsset = (id: unknown) => fakeAssets.assets.find((a) => a.id === String(id));
const current = (p: Product) => p.versions.find((v) => v.id === p.current_version_id);

/** 已锁定 / 待选 / 待生成, from the product (the backend's `_out`). */
function withStatus(a: Asset): Asset {
  const p = productOf(a);
  a.status = p?.locked_hash ? "locked" : p?.versions.length ? "choosing" : "not_generated";
  return a;
}

function announce(p: Product) {
  setTimeout(() =>
    injectEvent("product.updated", { product_id: p.id, series_id: p.series_id, status: p.status }),
  );
}

/** 锁定为参考: the picked candidate of the version on screen, as a locked `pick` version. */
function lock(a: Asset, p: Product, body: AssetLock): Response {
  if (p.locked_hash) return error(409, "product_locked", { id: p.id });
  const source = current(p);
  if (!source) return error(409, "nothing_to_lock", { id: a.id });
  if (!source.files.some((f) => f.role === "candidate")) {
    Object.assign(p, {
      adopted_version_id: source.id,
      locked_hash: source.content_hash,
      status: "locked",
    });
    announce(p);
    return HttpResponse.json(withStatus(a));
  }
  if (a.kind === "voice") return error(409, "voice_needs_final", { id: a.id });
  const file = source.files.find((f) => f.role === "candidate" && f.idx === a.pick);
  if (!file) return error(422, "no_such_candidate", { id: source.id, idx: a.pick });
  const parsed = CandidatesPayloadSchema.safeParse(source.payload);
  const made = parsed.success ? parsed.data : null;
  const cand = made?.candidates[a.pick];
  if (cand?.ocr_ok === false && !body.force)
    return error(409, "ocr_mismatch", {
      id: a.id,
      idx: a.pick,
      read: cand.ocr ?? "",
      exact: made?.text?.exact ?? "",
      issue: cand.ocr_issue ?? "",
    });
  const n = p.versions.length + 1;
  const pick: ProductVersion = {
    ...structuredClone(source),
    id: `${p.id}-v${n}`,
    n,
    origin: "pick",
    parent_version_id: source.id,
    payload: { candidate: {} },
    files: [{ ...file, role: "ref" }],
    content_hash: `sha256:${file.sha256}`,
  };
  p.versions.push(pick);
  Object.assign(p, {
    adopted_version_id: pick.id,
    locked_hash: pick.content_hash,
    status: "locked",
    pick: { version_id: source.id, idx: a.pick },
  });
  announce(p);
  return HttpResponse.json(withStatus(a));
}

/** What the candidates of a new version are: on-screen text is read by OCR, and the fake's
 * always matches (a base for compositing is blank). */
function candidatesOf(p: Product, count: number) {
  const a = fakeAssets.assets.find((x) => x.product_id === p.id);
  const text = a?.text;
  if (!text) return { candidates: Array.from({ length: count }, () => ({})) };
  const ocr = text.method === "composite" ? "" : text.exact;
  return {
    candidates: Array.from({ length: count }, () => ({ ocr, ocr_ok: true, ocr_issue: null })),
    text: { ...text },
  };
}

/** A new current version of `p` with `count` candidates (a run's, or one uploaded picture). */
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
    payload: candidatesOf(p, count),
    files: Array.from({ length: count }, (_, i) => ({
      role: "candidate",
      path: `blobs/sha256/00/${id}-${i}`,
      sha256: `${id}-${i}`,
      mime: p.component_id === "voice" ? "audio/wav" : "image/png",
      duration_s: null,
      w: 768,
      h: 1366,
      idx: i,
    })),
    content_hash: `sha256:${id}`,
    intent: p.prompt?.intent ?? "",
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
    cost_usd: 0,
    job_id: `job-${id}`,
    created_at: "2026-10-20T10:00:00Z",
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
    created_at: "2026-10-20T10:00:00Z",
    started_at: "2026-10-20T10:00:00Z",
    finished_at: "2026-10-20T10:00:01Z",
  };
}

/** 重跑: fresh candidates (4 pictures, 3 voices); 「用 API 出终版」 (`where: api` with the draft
 * as `params.source_version_id`): one picture on the API model, its parent the draft. */
const EMOTIONS = ["calm", "angry", "crying", "whisper", "shout"];
const audio = (id: string, role: string, extra: Partial<ProductVersion["files"][number]>) => ({
  role,
  path: `blobs/sha256/00/${id}`,
  sha256: id,
  mime: "audio/wav",
  duration_s: 1.5,
  w: null,
  h: null,
  idx: null,
  waveform: Array.from({ length: 64 }, (_, i) => ((i * 7) % 10) / 10),
  ...extra,
});

/** A voice's run: three auditions reading its lines, or (from one of them) its final. */
function runVoice(p: Product, body: RunRequest): Job {
  const source = body.params?.source_version_id;
  const local = body.where === "local";
  const model = !source
    ? "local/qwen3-tts"
    : local
      ? "local/indextts2"
      : (fakeResolve("voice", null)?.values.api_model ?? "minimax/speech-2.8-hd");
  const v = addVersion(p, 3, { origin: body.mode, model, stage: source ? "final" : "draft" });
  const a = fakeAssets.assets.find((x) => x.product_id === p.id);
  const lines = Math.max(1, a?.voice?.lines.length ?? 0);
  if (!source) {
    v.payload = {
      candidates: ["偏低沉", "更清亮", "带一点沙哑"].map((label) => ({ label })),
    };
    v.files = [0, 1, 2].flatMap((i) =>
      Array.from({ length: lines }, (_, j) =>
        audio(`${v.id}-${i}-${j}`, "candidate", { idx: i, line: j }),
      ),
    );
  } else {
    v.parent_version_id = source;
    v.payload = {
      provider: local ? "local" : "minimax",
      voice_id: local ? null : `voice-${v.id}`,
      emotions: EMOTIONS,
      label: "偏低沉",
    };
    v.files = [
      audio(`${v.id}-anchor`, "anchor", {}),
      ...EMOTIONS.map((emotion, k) =>
        audio(`${v.id}-${emotion}`, "variant", { idx: k, line: 0, emotion }),
      ),
    ];
  }
  return job(p, v.id, model, body.mode);
}

function run(p: Product, body: RunRequest): Job {
  if (p.component_id === "voice") return runVoice(p, body);
  const route = fakeResolve(p.component_id, null)?.values ?? null;
  const source = body.where === "api" ? body.params?.source_version_id : undefined;
  const model = source
    ? (route?.api_model ?? "google/nano-banana-pro")
    : (primaryModel(route) ?? "comfy/qwen-image");
  const count = source ? 1 : p.component_id === "voice" ? 3 : 4;
  const v = addVersion(p, count, {
    origin: body.mode,
    model,
    stage: source ? "final" : model.startsWith("comfy/") ? "draft" : null,
  });
  if (source) v.parent_version_id = source;
  return job(p, v.id, model, body.mode);
}

/** `asset_unlock`: what uses the locked picture (`assets/service.py:plan_unlock`), or null
 * when it is not locked. */
export function assetUnlockImpact(assetId: string): Pick<Impact, "lines" | "unaffected"> | null {
  const a = findAsset(assetId);
  const p = a && productOf(a);
  if (!a || !p?.locked_hash) return null;
  const views = fakeAssets.views.some((v) => v.owner_id === a.id);
  return {
    lines: [
      ...(views
        ? [{ code: "uses_ref_views", params: { name: a.name }, cost_usd: null, optional: false }]
        : []),
      ...assetShotLines(a.id),
    ],
    unaffected: { code: "unlock_keeps_ref", params: {} },
  };
}

export function unlockFakeAsset(assetId: string) {
  const a = findAsset(assetId);
  const p = a && productOf(a);
  if (!p) return;
  p.locked_hash = null;
  p.status = p.adopted_version_id ? "adopted" : "ready";
  if (a.scenes.length) fakeAssets.confirmed.delete(EPISODE);
  announce(p);
}

export function assetHandlers() {
  return [
    // `?episode=`: the fixture's are about episode 1 (`scenes`, `shots`).
    http.get("*/api/v1/series/:id/assets", ({ params }) =>
      HttpResponse.json(fakeAssets.assets.filter((a) => a.series_id === params.id).map(withStatus)),
    ),

    http.patch("*/api/v1/assets/:id", async ({ params, request }) => {
      const a = findAsset(params.id);
      const p = a && productOf(a);
      if (!a || !p) return error(404, "asset_not_found", { id: params.id });
      const body = AssetPatchSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const { intent, pick, text, voice } = body.data;
      if (p.locked_hash && (intent !== undefined || text || voice))
        return error(409, "product_locked", { id: p.id });
      if (intent !== undefined) {
        a.intent = intent;
        p.prompt = {
          intent,
          compiled: `[描述] ${intent}`,
          compiled_overridden: false,
          model_key: p.prompt?.model_key ?? "comfy/qwen-image",
        };
      }
      if (pick !== undefined) {
        if (!p.current_version_id) return error(409, "nothing_to_pick", { id: a.id });
        if (p.locked_hash) return error(409, "product_locked", { id: p.id });
        a.pick = pick;
        p.pick = { version_id: p.current_version_id, idx: pick };
      }
      if (text && a.text) a.text = { ...a.text, ...text };
      if (voice && a.voice) a.voice = { ...a.voice, ...voice };
      return HttpResponse.json(withStatus(a));
    }),

    http.post("*/api/v1/assets/:id/lock", async ({ params, request }) => {
      const a = findAsset(params.id);
      const p = a && productOf(a);
      if (!a || !p) return error(404, "asset_not_found", { id: params.id });
      const body = AssetLockSchema.safeParse(await request.json().catch(() => ({})));
      return lock(a, p, body.success ? body.data : {});
    }),

    http.post("*/api/v1/assets/:id/upload", async ({ params, request }) => {
      const a = findAsset(params.id);
      const p = a && productOf(a);
      if (!a || !p) return error(404, "asset_not_found", { id: params.id });
      if (a.kind === "voice") return error(422, "upload_not_supported", { kind: a.kind });
      if (p.locked_hash) return error(409, "product_locked", { id: p.id });
      const file = (await request.formData()).get("file");
      const name = file instanceof File ? file.name : "";
      fakeAssets.uploads.push({ id: a.id, name });
      const v = addVersion(p, 1, { origin: "upload", model: null, stage: null });
      v.note = name || null;
      a.pick = 0;
      p.pick = { version_id: v.id, idx: 0 };
      return HttpResponse.json(withStatus(a));
    }),

    http.post("*/api/v1/episodes/:id/assets/analyze", ({ params }) => {
      const id = String(params.id);
      fakeAssets.analyses.push(id);
      const p = fakeAssets.products[0];
      return p
        ? HttpResponse.json(job(p, `analyze-${id}`, "deepseek/v4.1-flash", "run"))
        : undefined;
    }),

    http.get("*/api/v1/episodes/:id/assets/matrix", ({ params }) =>
      params.id === demoMatrix.episode_id
        ? HttpResponse.json(demoMatrix)
        : error(404, "episode_not_found", { id: params.id }),
    ),

    http.get("*/api/v1/products", ({ request }) => {
      const owner = new URL(request.url).searchParams.get("owner") ?? "";
      if (!owner.startsWith("asset:")) return undefined;
      const id = owner.slice("asset:".length);
      const mine = [...fakeAssets.products, ...fakeAssets.views].filter((p) => p.owner_id === id);
      return HttpResponse.json(mine);
    }),

    http.get("*/api/v1/products/:id", ({ params }) => {
      const p = fakeAssets.products.find((x) => x.id === params.id);
      return p ? HttpResponse.json(p) : undefined;
    }),

    http.post("*/api/v1/products/:id/run", async ({ params, request }) => {
      const p = fakeAssets.products.find((x) => x.id === params.id);
      if (!p) return undefined;
      return HttpResponse.json(run(p, (await request.json()) as RunRequest));
    }),
  ];
}
