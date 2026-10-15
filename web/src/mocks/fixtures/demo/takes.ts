/**
 * Episode 1 video takes (prototype Generate.dc.html `baseTakes()` / `shots()`): each shot's
 * video product holds its takes as versions. 1-01–1-03 adopted (混合: local draft, then the
 * H3 API final), 1-04 has four takes to pick from, 1-05 is running, 1-06 / 1-07 queued,
 * 1-08 / 1-09 wait for the shot whose last frame they start from. QA over the 10 takes:
 * 6 pass, 4 fail; one automatic rerun, one automatic fallback.
 */
import type { GenerateLogEntry, GenerateRules } from "@/api/schemas/generate";
import type {
  Product,
  ProductVersion,
  QaCheck,
  QaIssue,
  QaResult,
  VersionOrigin,
} from "@/api/schemas/products";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { demoAt, demoCost, demoVersion } from "@/mocks/fixtures/demo/products";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import { shotId, videoProductId } from "@/mocks/fixtures/demo/shots";

export const PRODUCT_UPSCALE = "demo-p-up-e1";
export const PRODUCT_LIPSYNC = "demo-p-lip-e1";
export const PRODUCT_QA = "demo-p-qa-e1";

const DURATION: Record<string, number> = {
  "1-01": 4,
  "1-02": 3,
  "1-03": 3,
  "1-04": 4,
  "1-05": 3,
  "1-06": 5,
  "1-07": 2,
  "1-08": 6,
  "1-09": 4,
};

const na = (metric: QaCheck["metric"]): QaCheck => ({
  metric,
  value: null,
  text: null,
  issue: null,
  ok: null,
});
const score = (
  metric: QaCheck["metric"],
  value: number,
  ok: boolean,
  issue: QaIssue | null = null,
): QaCheck => ({ metric, value, text: null, issue, ok });
const ocr = (ok: boolean, text: string | null = null): QaCheck => ({
  metric: "ocr",
  value: null,
  text,
  issue: ok ? null : "text_mismatch",
  ok,
});
/** The vision model's finding is its own words (content), with a category code. */
const vlm = (issue: QaIssue | null = null, text: string | null = null): QaCheck => ({
  metric: "vlm",
  value: null,
  text,
  issue,
  ok: issue === null,
});

/** Score for 「推荐」: the face similarity where it applies (prototype `faceOf`). */
export function qaResult(checks: QaCheck[]): QaResult {
  const face = checks.find((c) => c.metric === "face");
  return { checks, score: face?.ok ? (face.value ?? 0) : 0 };
}

interface TakeSeed {
  model: string;
  at: string;
  origin?: VersionOrigin;
  stage?: "draft" | "final";
  fallback?: "timeout";
  checks: QaCheck[];
}

function takes(label: string, seeds: TakeSeed[]): ProductVersion[] {
  const productId = videoProductId(label);
  const list: ProductVersion[] = [];
  for (const [i, s] of seeds.entries()) {
    const v = demoVersion(productId, "vid", {
      n: i + 1,
      origin: s.origin ?? "run",
      model: s.model,
      at: demoAt(s.at),
      parent: list.at(-1)?.id ?? null,
      intent: SHOT_INTENT[label],
      payload: { duration_s: DURATION[label], resolution: "768p" },
    });
    const qa = qaResult(s.checks);
    list.push({
      ...v,
      qa,
      qa_pass: s.checks.every((c) => c.ok !== false),
      stage: s.stage ?? null,
      fallback_reason: s.fallback ?? null,
      cost_usd: demoCost(s.model, DURATION[label]),
    });
  }
  return list;
}

/** Same as the storyboard's picture descriptions (the video prompt's intent layer). */
const SHOT_INTENT: Record<string, string> = {
  "1-01": "楼道全景，声控灯忽明忽暗，林晚抱着画板袋走上六楼。",
  "1-02": "门口：红色长柄伞斜靠在墙边，伞柄上贴着黄色便利贴。",
  "1-03": "便利贴特写，歪扭的手写字，边角被雨打湿。",
  "1-04": "林晚低头看着便利贴，愣住，低声说话。声控灯在她脸上一明一暗。",
};

const LOCAL = "comfy/h3";
const H3_API = "minimax/h3-api";
const SILENT = [na("lipsync"), na("asr")];

const versions: Record<string, ProductVersion[]> = {
  "1-01": takes("1-01", [
    {
      model: LOCAL,
      at: "11:02",
      stage: "draft",
      checks: [score("face", 0.81, true), ...SILENT, na("ocr"), vlm()],
    },
    {
      model: H3_API,
      at: "11:06",
      stage: "final",
      checks: [score("face", 0.85, true), ...SILENT, na("ocr"), vlm()],
    },
  ]),
  "1-02": takes("1-02", [
    {
      model: LOCAL,
      at: "11:09",
      stage: "draft",
      checks: [na("face"), ...SILENT, na("ocr"), vlm("color_off", "伞的颜色偏橙")],
    },
    {
      model: H3_API,
      at: "11:13",
      stage: "final",
      checks: [na("face"), ...SILENT, na("ocr"), vlm()],
    },
  ]),
  "1-03": takes("1-03", [
    {
      model: LOCAL,
      at: "11:15",
      stage: "draft",
      checks: [na("face"), ...SILENT, ocr(false, "十二占"), vlm()],
    },
    {
      model: H3_API,
      at: "11:19",
      stage: "final",
      checks: [na("face"), ...SILENT, ocr(true), vlm()],
    },
  ]),
  "1-04": takes("1-04", [
    {
      model: LOCAL,
      at: "11:31",
      checks: [
        score("face", 0.71, false, "face_mismatch"),
        score("lipsync", 7.4, true),
        score("asr", 0, true),
        na("ocr"),
        vlm("finger_fusion", "手指粘连"),
      ],
    },
    {
      model: LOCAL,
      at: "11:38",
      origin: "auto_qa_rerun",
      checks: [
        score("face", 0.83, true),
        score("lipsync", 8.1, true),
        score("asr", 0, true),
        na("ocr"),
        vlm(),
      ],
    },
    {
      model: H3_API,
      at: "11:41",
      origin: "fallback",
      fallback: "timeout",
      checks: [
        score("face", 0.86, true),
        score("lipsync", 8.4, true),
        score("asr", 0, true),
        na("ocr"),
        vlm(),
      ],
    },
    {
      model: "volc/seedance-2.5",
      at: "11:52",
      origin: "switch",
      checks: [
        score("face", 0.79, true),
        score("lipsync", 7.9, true),
        score("asr", 0, true),
        na("ocr"),
        vlm("light_missing", "声控灯没有闪"),
      ],
    },
  ]),
};

const ADOPTED = new Set(["1-01", "1-02", "1-03"]);
/** 1-05 is on the GPU; 1-06 and 1-07 wait in the local queue, in this order. */
const IN_QUEUE: Record<string, Product["status"]> = {
  "1-05": "running",
  "1-06": "queued",
  "1-07": "queued",
};

function videoProduct(label: string): Product {
  const id = videoProductId(label);
  const list = versions[label] ?? [];
  const last = list.at(-1);
  const adopted = ADOPTED.has(label) ? last : undefined;
  const queued = IN_QUEUE[label];
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: "shot",
    owner_id: shotId(label),
    slot: "video",
    component_id: "vid",
    current_version_id: last?.id ?? null,
    adopted_version_id: adopted?.id ?? null,
    locked_hash: null,
    status: queued ?? (adopted ? "adopted" : last ? "ready" : "empty"),
    versions: list,
    prompt: null,
    estimate: null,
    running: queued ? { job_id: `demo-job-vid-${label}`, model_key: LOCAL } : null,
  };
}

function episodeProduct(
  id: string,
  slot: Product["slot"],
  componentId: string,
  first: { model: string; at: string } | null,
): Product {
  const v = first
    ? demoVersion(id, componentId, {
        n: 1,
        origin: "run",
        model: first.model,
        at: demoAt(first.at),
      })
    : undefined;
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: "episode",
    owner_id: EP1,
    slot,
    component_id: componentId,
    current_version_id: v?.id ?? null,
    adopted_version_id: v?.id ?? null,
    locked_hash: null,
    status: v ? "adopted" : "empty",
    versions: v ? [v] : [],
    prompt: null,
    estimate: null,
    running: null,
  };
}

export const takeProducts: Product[] = [
  ...Object.keys(DURATION).map(videoProduct),
  // 2K 精修 v1 SeedVR2 11:20 (1-01 至 1-03); 口型修复 none yet; 自动质检 v1 Qwen3-VL 10:58.
  episodeProduct(PRODUCT_UPSCALE, "upscale", "up", { model: "comfy/seedvr2", at: "11:20" }),
  episodeProduct(PRODUCT_LIPSYNC, "lipsync", "lip", null),
  episodeProduct(PRODUCT_QA, "qa", "qa", { model: "local/qwen3-vl-32b", at: "10:58" }),
];

/** Prototype 自动规则 and components.yaml `qa.thresholds`. */
export const generateRules: GenerateRules = {
  takes_per_shot: 3,
  qa_retry_max: 2,
  shot_cap_usd: 2,
  thresholds: { face_sim: 0.75, syncnet_conf: 6, cer_max: 0.1 },
};

const entry = (
  at: string,
  shot: string,
  code: string,
  params: Record<string, string | number>,
  warn = false,
): GenerateLogEntry => ({
  id: `demo-log-${at}-${shot}`,
  at: demoAt(at),
  shot_label: shot,
  message: { code, params },
  warn,
});

/** 运行记录, oldest first (the page shows the newest first). */
export const generateLog: GenerateLogEntry[] = [
  entry(
    "11:31",
    "1-04",
    "take_fail_rerun",
    { model: LOCAL, take: 1, fails: 2, issues: "face_mismatch,finger_fusion" },
    true,
  ),
  entry("11:38", "1-04", "take_pass", { model: LOCAL, take: 2, cost_usd: 0 }),
  entry("11:40", "1-04", "fallback_timeout", { model: H3_API, minutes: 10 }, true),
  entry("11:41", "1-04", "take_pass", { model: H3_API, take: 3, cost_usd: 0.32 }),
  entry(
    "11:52",
    "1-04",
    "switch_fail",
    { model: "volc/seedance-2.5", take: 4, cost_usd: 1.64, fails: 1 },
    true,
  ),
  entry("11:55", "1-05", "started", { model: LOCAL }),
];
