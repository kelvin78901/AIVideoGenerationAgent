/**
 * Helpers for the demo's products and versions (assets, shots, takes, post). The novel and
 * script steps' — 小说补全 v1 Qwen3.6-27B 本地 09:41 → v2 DeepSeek V4 Pro 10:02, 设定提取 v1 本地
 * 10:05, 分集规划 v1 DeepSeek V4.1 Flash 10:08, 第 1 集剧本化 v1 本地 10:12 → v2 Kimi K2.6 10:20
 * (prototype Main.dc.html, Inspector「历史」) — are the backend's (`studio/demo.py`), merged into
 * the demo's product lists by `handlers/products.ts`.
 */
import type { Product, ProductVersion, VersionOrigin } from "@/api/schemas/products";
import { modelByKey } from "@/mocks/fixtures/demo/models";
import { compilePrompt, intents } from "@/mocks/fixtures/demo/prompts";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

/** The backend's 小说补全 and 设定提取 products of the demo series (seeded in Mock mode). */
export const PRODUCT_ENRICH = "demo-p-enrich";
export const PRODUCT_EXTRACT = "demo-p-extract";

/**
 * 2026-10-14 at a wall-clock time in the viewer's time zone, so the demo shows the prototype's
 * 09:41 / 10:02 / 10:05 wherever it runs.
 */
export function demoAt(hhmm: string): string {
  const [h = 0, m = 0] = hhmm.split(":").map(Number);
  return new Date(2026, 9, 14, h, m).toISOString();
}

/**
 * Mock-mode cost of one run: a writing call is ~8k tokens in, ~3k out; an image run makes
 * `units` candidates (default 4); a video take is `units` seconds; a voice run is one voice
 * design ($3, providers.yaml `extras.voice_design`).
 */
export function demoCost(modelKey: string, units = 4): number {
  const m = modelByKey(modelKey);
  if (!m || m.where === "local") return 0;
  if (m.price?.unit === "image" || m.price?.unit === "second")
    return Math.round(m.price.amount * units * 100) / 100;
  if (m.price?.unit === "mchar") return 3;
  if (!m.price || m.price.unit !== "mtok") return 0.02;
  const usd = (m.price.in * 8000 + m.price.out * 3000) / 1e6;
  const rate = m.price.currency === "CNY" ? 1 / 7.1 : 1;
  return Math.max(0.01, Math.round(usd * rate * 100) / 100);
}

function candidateCount(payload: Record<string, unknown> | undefined): number | undefined {
  const c = payload?.candidates;
  return Array.isArray(c) ? c.length : undefined;
}

export function demoVersion(
  productId: string,
  componentId: string,
  v: {
    n: number;
    origin: VersionOrigin;
    model: string;
    at: string;
    parent?: string | null;
    intent?: string;
    compiled?: string;
    payload?: Record<string, unknown>;
  },
): ProductVersion {
  const intent = v.intent ?? intents[componentId] ?? "";
  return {
    id: `${productId}-v${v.n}`,
    product_id: productId,
    n: v.n,
    origin: v.origin,
    parent_version_id: v.parent ?? null,
    payload: v.payload ?? {},
    files: [],
    content_hash: `sha256:${productId}-v${v.n}`,
    intent,
    compiled: v.compiled ?? compilePrompt(componentId, intent, v.model),
    compiled_overridden: v.compiled !== undefined,
    model_key: v.model,
    where: modelByKey(v.model)?.where ?? "api",
    seed: 1000 + v.n,
    params: {},
    qa: null,
    qa_pass: null,
    fallback_reason: null,
    stage: null,
    rating: null,
    cost_usd: demoCost(v.model, candidateCount(v.payload)),
    job_id: null,
    created_at: v.at,
    note: null,
  };
}

const LOCAL = "local/qwen3.6-27b";

/** A demo product owned by the series (default) or an episode, with its versions. */
export function demoProduct(
  id: string,
  componentId: string,
  slot: Product["slot"],
  versions: ProductVersion[],
  seconds: number,
  owner: { type: Product["owner_type"]; id: string } = { type: "series", id: DEMO_SERIES_ID },
  model0 = LOCAL,
): Product {
  const last = versions[versions.length - 1];
  const model = last?.model_key ?? model0;
  const intent = last?.intent ?? intents[componentId] ?? "";
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: owner.type,
    owner_id: owner.id,
    slot,
    component_id: componentId,
    current_version_id: last?.id ?? null,
    adopted_version_id: last?.id ?? null,
    locked_hash: null,
    status: last ? "adopted" : "empty",
    versions,
    prompt: {
      intent,
      compiled: last?.compiled ?? compilePrompt(componentId, intent, model),
      compiled_overridden: false,
      model_key: model,
    },
    estimate: {
      model_key: model,
      where: modelByKey(model)?.where ?? "api",
      cost_usd: demoCost(model),
      seconds,
    },
    running: null,
  };
}
