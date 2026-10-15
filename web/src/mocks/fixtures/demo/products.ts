/**
 * Products and versions for the novel step (prototype Main.dc.html, Inspector「历史」):
 * 小说补全 v1 Qwen3.6-27B 本地 09:41 草稿 → v2 DeepSeek V4 Pro 10:02（不满意换一个）已采纳；
 * 设定提取 v1 Qwen3.6-27B 本地 10:05 已采纳.
 */
import type { Product, ProductVersion, VersionOrigin } from "@/api/schemas/products";
import { modelByKey } from "@/mocks/fixtures/demo/models";
import { compilePrompt, intents } from "@/mocks/fixtures/demo/prompts";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

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

/** Mock-mode cost of one writing call: ~8k tokens in, ~3k out at the list price. */
export function demoCost(modelKey: string): number {
  const m = modelByKey(modelKey);
  if (!m || m.where === "local") return 0;
  if (!m.price || m.price.unit !== "mtok") return 0.02;
  const usd = (m.price.in * 8000 + m.price.out * 3000) / 1e6;
  const rate = m.price.currency === "CNY" ? 1 / 7.1 : 1;
  return Math.max(0.01, Math.round(usd * rate * 100) / 100);
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
    cost_usd: demoCost(v.model),
    job_id: null,
    created_at: v.at,
    note: null,
  };
}

const LOCAL = "local/qwen3.6-27b";
const DEEPSEEK = "deepseek/v4-pro";

function novelProduct(
  id: string,
  componentId: string,
  slot: Product["slot"],
  versions: ProductVersion[],
  seconds: number,
): Product {
  const last = versions[versions.length - 1];
  const model = last?.model_key ?? LOCAL;
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: "series",
    owner_id: DEMO_SERIES_ID,
    slot,
    component_id: componentId,
    current_version_id: last?.id ?? null,
    adopted_version_id: last?.id ?? null,
    locked_hash: null,
    status: "adopted",
    versions,
    prompt: {
      intent: last?.intent ?? "",
      compiled: last?.compiled ?? "",
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

const enrichV1 = demoVersion(PRODUCT_ENRICH, "enrich", {
  n: 1,
  origin: "run",
  model: LOCAL,
  at: demoAt("09:41"),
  payload: { suggestions: 4 },
});

export const products: Product[] = [
  novelProduct(
    PRODUCT_ENRICH,
    "enrich",
    "suggestions",
    [
      enrichV1,
      demoVersion(PRODUCT_ENRICH, "enrich", {
        n: 2,
        origin: "switch",
        model: DEEPSEEK,
        at: demoAt("10:02"),
        parent: enrichV1.id,
        payload: { suggestions: 4 },
      }),
    ],
    40,
  ),
  novelProduct(
    PRODUCT_EXTRACT,
    "extract",
    "bible",
    [
      demoVersion(PRODUCT_EXTRACT, "extract", {
        n: 1,
        origin: "run",
        model: LOCAL,
        at: demoAt("10:05"),
        payload: { characters: 2, locations: 3, props: 4 },
      }),
    ],
    60,
  ),
];
