/**
 * Episode 1 assets (prototype Assets.dc.html `assets()`): 13 items, 7 locked, 3 waiting for a
 * pick, 3 not generated. Each asset owns one product; its versions carry the candidates.
 */
import type { Asset, CandidatesPayload } from "@/api/schemas/assets";
import type { Product, ProductVersion } from "@/api/schemas/products";
import { demoAt, demoVersion } from "@/mocks/fixtures/demo/products";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

type Seed = Omit<Asset, "series_id" | "product_id" | "status" | "pick" | "text" | "voice"> &
  Partial<Pick<Asset, "text" | "voice">> & { state: "locked" | "choosing" | "none" };

const msg = (code: string, params: Record<string, string | number> = {}) => ({ code, params });

const seeds: Seed[] = [
  {
    id: "linwan",
    kind: "character",
    name: "林晚",
    state: "locked",
    source: msg("script_line", { scene: 1, line: 1 }),
    shots: ["1-01", "1-04", "1-05", "1-06", "1-08", "1-09"],
    intent:
      "26 岁女性，插画师。米色风衣湿了半边，低马尾，素颜，左手腕一根旧黑发圈。神情疲惫但克制。",
  },
  {
    id: "zhouyu",
    kind: "character",
    name: "周屿",
    state: "none",
    source: msg("script_line_note", { scene: 1, line: 3, note: "本集只出现字迹" }),
    shots: [],
    intent: "外貌待定，第 2 集出场前再做。",
  },
  {
    id: "hall",
    kind: "scene",
    name: "老小区楼道 · 夜",
    state: "locked",
    source: msg("scene_heading", { scene: 1 }),
    shots: ["1-01", "1-02", "1-03", "1-04", "1-05"],
    intent: "六层老楼的楼道，水泥台阶，墙皮剥落；声控灯偏黄，坏了一半；窗外下大雨，地上有湿脚印。",
  },
  {
    id: "room",
    kind: "scene",
    name: "林晚出租屋 · 夜",
    state: "choosing",
    source: msg("scene_heading", { scene: 2 }),
    shots: ["1-06", "1-07", "1-08", "1-09"],
    intent: "十来平米的出租屋，门后挂着画板，桌上堆着画稿；只开一盏台灯，暖光；旧的绿色铁门。",
  },
  {
    id: "store",
    kind: "scene",
    name: "楼下便利店 · 夜",
    state: "none",
    source: msg("episode_scene", { episode: 2, scene: 3 }),
    shots: [],
    intent: "第 2 集才出现，到时再做。",
  },
  {
    id: "umbrella",
    kind: "prop",
    name: "红色长柄伞",
    state: "locked",
    source: msg("script_line", { scene: 1, line: 2 }),
    shots: ["1-02", "1-08", "1-09"],
    intent: "正红色长柄直伞，木质弯柄，伞面是湿的，收着靠墙。",
  },
  {
    id: "note",
    kind: "prop",
    name: "黄色便利贴",
    state: "locked",
    source: msg("script_line", { scene: 1, line: 2 }),
    shots: ["1-02", "1-03", "1-05"],
    intent: "方形黄色便利贴，贴在伞柄上，边角被雨打湿卷起。上面的字另做（见画面文字）。",
  },
  {
    id: "band",
    kind: "prop",
    name: "旧黑发圈",
    state: "choosing",
    source: msg("script_line", { scene: 1, line: 4 }),
    shots: ["1-05"],
    intent: "洗旧了的黑色布发圈，戴在林晚左手腕上。",
  },
  {
    id: "phone",
    kind: "prop",
    name: "手机",
    state: "locked",
    source: msg("script_line", { scene: 2, line: 2 }),
    shots: ["1-07"],
    intent: "普通全面屏手机，黑色壳，屏幕有一道细划痕。锁屏内容另做（见画面文字）。",
  },
  {
    id: "txt1",
    kind: "text",
    name: "便利贴手写",
    state: "choosing",
    source: msg("script_line", { scene: 1, line: 3 }),
    shots: ["1-03"],
    intent: "黑色圆珠笔手写，字迹歪扭但能认清，写在黄色便利贴上。",
    text: { exact: "楼下便利店，等你到十二点。", method: "model", style: "handwritten" },
  },
  {
    id: "txt2",
    kind: "text",
    name: "手机锁屏时间",
    state: "locked",
    source: msg("script_line", { scene: 2, line: 2 }),
    shots: ["1-07"],
    intent: "手机锁屏上的大号时间，白字，系统默认字体，下方没有通知。",
    text: { exact: "23:52", method: "composite", style: "screen" },
  },
  {
    id: "vlinwan",
    kind: "voice",
    name: "林晚",
    state: "locked",
    source: msg("dialogue_count", { count: 2 }),
    shots: ["1-04", "1-06"],
    intent: "二十多岁女声，偏低，克制，句尾轻，不要播音腔。",
    voice: {
      method: "design",
      lines: [
        { text: "……周屿？", tone: "低声，愣住" },
        { text: "三年了。他凭什么。", tone: "画外音，压着火" },
      ],
    },
  },
  {
    id: "vzhouyu",
    kind: "voice",
    name: "周屿",
    state: "none",
    source: msg("episode", { episode: 2 }),
    shots: [],
    intent: "第 2 集出场前再定。",
    voice: { method: "design", lines: [] },
  },
];

export const assetProductId = (assetId: string) => `demo-p-asset-${assetId}`;

const componentOf = (kind: Asset["kind"]) =>
  kind === "voice" ? "voice" : kind === "text" ? "text" : "img";
const slotOf = (kind: Asset["kind"]): Product["slot"] =>
  kind === "voice" ? "voice" : kind === "text" ? "text_image" : "ref_image";

const WAVES = [
  [10, 18, 26, 14, 22, 30, 12, 20, 16, 28, 10, 18, 24, 12, 20, 14],
  [14, 22, 12, 28, 18, 10, 24, 30, 16, 12, 22, 18, 10, 26, 14, 20],
  [8, 16, 22, 30, 12, 18, 26, 10, 20, 28, 14, 10, 24, 16, 22, 12],
].map((w) => w.map((h) => h / 30));
const VOICE_LABELS = ["偏低沉", "更清亮", "带一点沙哑"];

/** Candidates a run produces for an asset (4 images, 4 text images with OCR, 3 voices). */
export function candidatesFor(asset: {
  kind: Asset["kind"];
  text?: Asset["text"];
}): CandidatesPayload {
  if (asset.kind === "voice")
    return {
      candidates: VOICE_LABELS.map((label, i) => ({ label, waveform: WAVES[i] ?? null })),
    };
  const exact = asset.text?.exact;
  return {
    candidates: [0, 1, 2, 3].map((i) => {
      if (exact === undefined) return {};
      // Model-drawn text misreads now and then (prototype): 点 → 占, a dropped last character.
      if (asset.text?.method === "composite") return { ocr: exact };
      if (i === 1) return { ocr: exact.replace("点", "占") };
      if (i === 3) return { ocr: exact.slice(0, -1) };
      return { ocr: exact };
    }),
  };
}

function versionsOf(seed: Seed, productId: string): ProductVersion[] {
  if (seed.state === "none") return [];
  const component = componentOf(seed.kind);
  const payload = candidatesFor(seed);
  const v = (n: number, model: string, at: string, parent: string | null = null) =>
    demoVersion(productId, component, {
      n,
      origin: "run",
      model,
      at: demoAt(at),
      parent,
      intent: seed.intent,
      payload,
    });
  if (seed.id === "linwan") {
    // 混合: 本地草稿, then the API final (SPEC 7.7).
    const draft = v(1, "comfy/qwen-image-edit", "10:31");
    return [draft, v(2, "google/nano-banana-pro", "10:36", draft.id)];
  }
  if (seed.kind === "voice") return [v(1, "minimax/speech-2.8-hd", "10:40")];
  if (seed.kind === "text") return [v(1, "openai/gpt-image-2", "10:44")];
  return [v(1, "comfy/qwen-image-edit", "10:33")];
}

function productOf(seed: Seed): Product {
  const id = assetProductId(seed.id);
  const versions = versionsOf(seed, id);
  const last = versions.at(-1);
  const locked = seed.state === "locked" && last;
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: "asset",
    owner_id: seed.id,
    slot: slotOf(seed.kind),
    component_id: componentOf(seed.kind),
    current_version_id: last?.id ?? null,
    adopted_version_id: locked ? last.id : null,
    locked_hash: locked ? last.content_hash : null,
    status: locked ? "locked" : last ? "ready" : "empty",
    versions,
    prompt: null,
    estimate: null,
    running: null,
  };
}

export const assets: Asset[] = seeds.map(
  ({ id, kind, name, intent, source, shots, text, voice }) => ({
    id,
    kind,
    name,
    intent,
    source,
    shots,
    series_id: DEMO_SERIES_ID,
    product_id: assetProductId(id),
    status: "not_generated",
    pick: 0,
    text: text ?? null,
    voice: voice ?? null,
  }),
);

export const assetProducts: Product[] = seeds.map(productOf);
