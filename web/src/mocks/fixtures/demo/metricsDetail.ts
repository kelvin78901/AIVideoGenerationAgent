/**
 * Lower half of the dashboard (prototype Dashboard.dc.html `SH`, `COMP`, `SP`, `API`, `LOC`, `QA`,
 * `epRows`): per-shot time and money, components, speed, APIs, local models, QA, episodes.
 */
import type { Message } from "@/api/schemas/common";
import type {
  ApiMetrics,
  ComponentMetrics,
  EpisodeMetrics,
  LocalModelMetrics,
  QaMetrics,
  ShotMetric,
  ShotMetrics,
  SpeedMetrics,
} from "@/api/schemas/metrics";

const m = (code: string, params: Message["params"] = {}): Message => ({ code, params });
const min = (n: number) => n * 60;

function shot(
  shot_id: string,
  scene: number,
  title: string,
  [kf, vid, post]: [number, number, number],
  rest: Partial<ShotMetric> & Pick<ShotMetric, "status">,
): ShotMetric {
  return {
    shot_id,
    scene,
    title,
    stage_seconds: { kf: min(kf), vid: min(vid), post: min(post) },
    cost_usd: 0,
    takes: 0,
    waiting_for: null,
    notes: [],
    take_chain: [],
    ...rest,
  };
}

export const shotMetrics: ShotMetrics = {
  scenes: [
    { scene: 1, title: "楼道" },
    { scene: 2, title: "出租屋" },
  ],
  shots: [
    shot("1-01", 1, "楼道全景", [6, 9, 7], {
      status: "adopted",
      cost_usd: 0.74,
      takes: 2,
      notes: [
        m("kf_draft_final", { model: "Nano Banana Pro" }),
        m("vid_draft_final", { model: "H3 API" }),
        m("upscaled", { model: "SeedVR2", minutes: 4 }),
      ],
    }),
    shot("1-02", 1, "门口的红伞", [5, 8, 6], {
      status: "adopted",
      cost_usd: 0.66,
      takes: 2,
      notes: [m("draft_failed_final_passed", { issues: "color_off" })],
    }),
    shot("1-03", 1, "便利贴特写", [5, 9, 5], {
      status: "adopted",
      cost_usd: 0.66,
      takes: 2,
      notes: [m("ocr_failed_final_exact", { read: "十二占" })],
    }),
    shot("1-04", 1, "林晚：……周屿？", [4, 31, 3], {
      status: "picking",
      cost_usd: 1.96,
      takes: 4,
      take_chain: [
        m("local_failed", { take: "T1", minutes: 7.5, issues: "face_mismatch,finger_fusion" }),
        m("auto_rerun", { take: "T2", minutes: 7.5 }),
        m("timeout_fallback", { take: "T3", minutes: 10, model: "H3 API", fallback_minutes: 1 }),
        m("switch_failed", {
          take: "T4",
          model: "Seedance 2.5",
          minutes: 3,
          issues: "light_missing",
        }),
      ],
    }),
    shot("1-05", 1, "指尖、旧发圈", [4, 6, 0], {
      status: "generating",
      notes: [m("generating", { model: "H3", n: 1, minutes: 6 })],
    }),
    shot("1-06", 2, "背靠着门", [4, 0, 0], { status: "queued", notes: [m("kf_done_queued")] }),
    shot("1-07", 2, "手机 23:52", [3, 0, 0], { status: "queued", notes: [m("kf_done_queued")] }),
    shot("1-08", 2, "开门，关门，再开门", [0, 0, 0], {
      status: "waiting",
      waiting_for: "1-06",
      notes: [m("waits_tail", { shot: "1-06" })],
    }),
    shot("1-09", 2, "拿起伞（卡点）", [0, 0, 0], {
      status: "waiting",
      waiting_for: "1-08",
      notes: [m("waits_tail", { shot: "1-08" })],
    }),
  ],
};

/** Local 132 min, waiting on APIs 44 min (prototype `COMP`; 设定提取、分集 split in two). */
export const componentMetrics: ComponentMetrics = {
  rows: (
    [
      ["vid", 51, 12],
      ["kf", 25, 6],
      ["img", 22, 8],
      ["qa", 12, 0],
      ["script", 4, 5],
      ["up", 9, 0],
      ["text", 3, 4],
      ["enrich", 3, 2],
      ["voice", 1, 3],
      ["plan", 0, 3],
      ["extract", 1, 1],
      ["split", 1, 0],
    ] as const
  ).map(([component, local, api]) => ({
    component,
    local_seconds: min(local),
    api_seconds: min(api),
  })),
};

export const speedMetrics: SpeedMetrics = {
  example_output_s: 4,
  rows: [
    {
      model: "MiniMax H3",
      where: "local",
      price: null,
      median: 112,
      min: 98,
      max: 150,
      samples: 6,
    },
    {
      model: "Seedance 2.5",
      where: "api",
      price: { unit: "second", amount: 0.41, currency: "USD" },
      median: 48,
      min: 48,
      max: 48,
      samples: 1,
    },
    { model: "SeedVR2 2K", where: "local", price: null, median: 45, min: 40, max: 52, samples: 3 },
    {
      model: "MiniMax H3",
      where: "api",
      price: { unit: "second", amount: 0.08, currency: "USD" },
      median: 15,
      min: 13,
      max: 18,
      samples: 4,
    },
  ],
  notes: [m("timeout_fallback", { model: "H3", minutes: 10 })],
};

const usd = (amount: number, unit: "image" | "second" | "call" | "mchar") =>
  ({ unit, amount, currency: "USD" }) as const;
const mtok = (inp: number, out: number) =>
  ({ unit: "mtok", in: inp, out, currency: "USD" }) as const;

/** Σ cost $8.94, 42 calls, 41 succeeded (97.6%). */
export const apiMetrics: ApiMetrics = {
  total_cost_usd: 8.94,
  rows: [
    {
      model: "MiniMax Speech 2.8 HD",
      kind: "av",
      calls: 4,
      succeeded: 4,
      canceled: 0,
      median_latency_s: 18,
      usage: m("voice", { designs: 1, chars: 412 }),
      prices: [usd(3, "call"), usd(100, "mchar")],
      cost_usd: 3.04,
      note: null,
    },
    {
      model: "Nano Banana Pro",
      kind: "image",
      calls: 13,
      succeeded: 13,
      canceled: 0,
      median_latency_s: 14,
      usage: m("images_split", { n: 13, ref: 4, kf: 9 }),
      prices: [usd(0.14, "image")],
      cost_usd: 1.82,
      note: null,
    },
    {
      model: "Seedance 2.5",
      kind: "av",
      calls: 1,
      succeeded: 1,
      canceled: 0,
      median_latency_s: 190,
      usage: m("video_seconds", { s: 4 }),
      prices: [usd(0.41, "second")],
      cost_usd: 1.64,
      note: null,
    },
    {
      model: "MiniMax H3 API",
      kind: "av",
      calls: 5,
      succeeded: 4,
      canceled: 0,
      median_latency_s: 62,
      usage: m("video_seconds", { s: 14 }),
      prices: [usd(0.08, "second")],
      cost_usd: 1.12,
      note: m("rate_limited", { n: 1 }),
    },
    {
      model: "GPT Image 2",
      kind: "image",
      calls: 4,
      succeeded: 4,
      canceled: 0,
      median_latency_s: 38,
      usage: m("images_for", { n: 4, component: "text" }),
      prices: [usd(0.28, "image")],
      cost_usd: 1.12,
      note: null,
    },
    {
      model: "DeepSeek V4 Pro",
      kind: "text",
      calls: 9,
      succeeded: 9,
      canceled: 0,
      median_latency_s: 21,
      usage: m("tokens", { in: 61, out: 18 }),
      prices: [mtok(1.32, 3.96)],
      cost_usd: 0.15,
      note: null,
    },
    {
      model: "Kimi K2.6",
      kind: "text",
      calls: 2,
      succeeded: 2,
      canceled: 0,
      median_latency_s: 26,
      usage: m("tokens", { in: 14, out: 6 }),
      prices: [mtok(0.95, 4)],
      cost_usd: 0.04,
      note: null,
    },
    {
      model: "DeepSeek V4.1 Flash",
      kind: "text",
      calls: 4,
      succeeded: 4,
      canceled: 0,
      median_latency_s: 6,
      usage: m("tokens", { in: 22, out: 5 }),
      prices: [mtok(0.3, 1.2)],
      cost_usd: 0.01,
      note: null,
    },
  ],
};

export const localModelMetrics: LocalModelMetrics = {
  vram_total_gb: 32,
  rows: [
    { model: "MiniMax H3", components: ["vid"], runs: 7, seconds: min(51), vram_peak_gb: 29.6 },
    {
      model: "Qwen-Image-Edit",
      components: ["img", "kf"],
      runs: 16,
      seconds: min(47),
      vram_peak_gb: 21.4,
    },
    { model: "Qwen3-VL-32B", components: ["qa"], runs: 10, seconds: min(12), vram_peak_gb: 22.5 },
    {
      model: "Qwen3.6-27B",
      components: ["enrich", "extract", "script"],
      runs: 4,
      seconds: min(9),
      vram_peak_gb: 18.9,
    },
    { model: "SeedVR2", components: ["up"], runs: 3, seconds: min(9), vram_peak_gb: 23.8 },
    { model: "Qwen-Image", components: ["text"], runs: 1, seconds: min(3), vram_peak_gb: 20.1 },
    { model: "IndexTTS2", components: ["dub"], runs: 2, seconds: min(1), vram_peak_gb: 5.7 },
  ],
  notes: [m("vram_tight", { model: "MiniMax H3", peak: 29.6, total: 32, left: 2.4 })],
};

/** 10 video takes: 6 passed, 4 failed (a take can fail on several checks). */
export const qaMetrics: QaMetrics = {
  passed: 6,
  failed: 4,
  issues: [
    { issue: "face_mismatch", count: 1 },
    { issue: "finger_fusion", count: 1 },
    { issue: "color_off", count: 1 },
    { issue: "light_missing", count: 1 },
    { issue: "text_mismatch", count: 1 },
  ],
  auto_reruns: 1,
  auto_fallbacks: 1,
  manual_switches: 1,
};

export const episodeMetrics: EpisodeMetrics = {
  rows: [
    {
      episode_id: "demo-e1",
      idx: 1,
      title: "红伞",
      stage: "in_progress",
      adopted_seconds: 10,
      total_seconds: 34,
      total_estimated: false,
      spent_usd: 8.94,
      projected_usd: 13.35,
      reuses_assets: false,
      compute_seconds: min(176),
    },
    {
      episode_id: "demo-e2",
      idx: 2,
      title: "十二点",
      stage: "script_pending",
      adopted_seconds: 0,
      total_seconds: 70,
      total_estimated: true,
      spent_usd: 0,
      projected_usd: 7.1,
      reuses_assets: true,
      compute_seconds: null,
    },
    {
      episode_id: "demo-e3",
      idx: 3,
      title: "旧发圈",
      stage: "not_started",
      adopted_seconds: 0,
      total_seconds: 80,
      total_estimated: true,
      spent_usd: 0,
      projected_usd: 7.6,
      reuses_assets: false,
      compute_seconds: null,
    },
  ],
};

/** `model_call` rows for `/metrics/export.csv` (one per call; SPEC 11.1). */
export const CSV_HEADER = [
  "time",
  "kind",
  "shot",
  "model",
  "where",
  "duration_s",
  "usage",
  "cost_usd",
  "result",
] as const;
