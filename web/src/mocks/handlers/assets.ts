import { http } from "msw";

import { AssetPatchSchema, type Asset, type CandidatesPayload } from "@/api/schemas/assets";
import type { Impact } from "@/api/schemas/impact";
import type { Product } from "@/api/schemas/products";
import { getDb } from "@/mocks/db";
import { candidatesFor } from "@/mocks/fixtures/demo/assets";
import { compilePrompt } from "@/mocks/fixtures/demo/prompts";
import { demoError, demoJson, v1 } from "@/mocks/http";

const productOf = (a: Asset): Product | undefined => getDb().products[a.product_id];
const findAsset = (id: unknown) => getDb().assets.find((x) => x.id === String(id));

/** 已锁定 / 待选 / 待生成 follow the asset's product. */
export function withStatus(a: Asset): Asset {
  const p = productOf(a);
  a.status = p?.locked_hash ? "locked" : p?.versions.length ? "choosing" : "not_generated";
  return a;
}

export function lockedAssetCount(): { done: number; total: number } {
  const list = getDb().assets.map(withStatus);
  return { done: list.filter((a) => a.status === "locked").length, total: list.length };
}

/** Candidates for a new version of an asset product (the current text and method count). */
export function assetPayload(p: Product): CandidatesPayload | undefined {
  if (p.owner_type !== "asset") return undefined;
  const a = findAsset(p.owner_id);
  return a ? candidatesFor(a) : undefined;
}

/** Unlocking a locked asset: the shots that use it as a reference go stale. */
export function assetUnlockPreview(assetId: string): Omit<Impact, "id" | "change"> | undefined {
  const a = findAsset(assetId);
  if (!a) return undefined;
  const n = a.shots.length;
  const cost = Math.round(n * 0.14 * 100) / 100;
  return {
    lines: n
      ? [
          {
            code: "shot_refs",
            params: { ids: a.shots.join(" "), count: n },
            cost_usd: null,
            optional: false,
          },
          { code: "keyframes", params: { count: n }, cost_usd: cost, optional: false },
        ]
      : [],
    unaffected: { code: "unlock_keeps_adopted", params: {} },
    rerun_cost_usd: cost,
    stale: n ? { storyboard: n, generate: n } : {},
  };
}

export function applyAssetUnlock(assetId: string): void {
  const a = findAsset(assetId);
  const p = a && productOf(a);
  if (!p) return;
  p.locked_hash = null;
  p.status = p.adopted_version_id ? "adopted" : "ready";
}

export const assetHandlers = [
  http.get(v1("/series/:id/assets"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().series[id]) return demoError(404, "series_not_found", { id });
    return demoJson(
      getDb()
        .assets.filter((a) => a.series_id === id)
        .map(withStatus),
    );
  }),

  http.patch(v1("/assets/:id"), async ({ params, request }) => {
    const a = findAsset(params.id);
    if (!a) return demoError(404, "asset_not_found", { id: params.id });
    const body = AssetPatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const { intent, pick, text, voice } = body.data;
    if (pick !== undefined) a.pick = pick;
    if (text && a.text) a.text = { ...a.text, ...text };
    if (voice && a.voice) a.voice = { ...a.voice, ...voice };
    const p = productOf(a);
    if (intent !== undefined) {
      a.intent = intent;
      // The description is the intent layer: the next run uses it.
      if (p) {
        const model = p.prompt?.model_key ?? p.versions.at(-1)?.model_key ?? "";
        p.prompt = {
          intent,
          compiled: compilePrompt(p.component_id, intent, model),
          compiled_overridden: false,
          model_key: model,
        };
      }
    }
    return demoJson(withStatus(a));
  }),

  // 锁定为参考: adopt the version on screen with the picked candidate, then lock it.
  http.post(v1("/assets/:id/lock"), ({ params }) => {
    const a = findAsset(params.id);
    const p = a && productOf(a);
    if (!a || !p) return demoError(404, "asset_not_found", { id: params.id });
    const v = p.versions.find((x) => x.id === p.current_version_id) ?? p.versions.at(-1);
    if (!v) return demoError(409, "nothing_adopted", { id: p.id });
    p.adopted_version_id = v.id;
    p.locked_hash = v.content_hash;
    p.status = "locked";
    return demoJson(withStatus(a));
  }),

  // 重新分析剧本: the demo script has not changed since the last analysis.
  http.post(v1("/episodes/:id/assets/analyze"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().episodes.some((e) => e.id === id))
      return demoError(404, "episode_not_found", { id });
    return demoJson({ added: 0, changed: 0 });
  }),
];
