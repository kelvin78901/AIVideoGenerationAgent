/** Dashboard numbers (prototype Dashboard; SPEC 11.2): spent $8.94, projected $13.35, budget $15. */
import type { Message } from "@/api/schemas/common";
import type {
  CallsSeries,
  MetricsKpis,
  MetricsScope,
  MetricsSummary,
  SpendSeries,
} from "@/api/schemas/metrics";

const insights: MetricsSummary["insights"] = [
  { code: "one_off_assets", params: { voice: 3.04, images: 1.68, share: 53 } },
  { code: "slowest_shot", params: { shot: "1-04", minutes: 31 } },
  {
    code: "pricey_model",
    params: { model: "Seedance 2.5", price: 0.41, vs: "H3 API", ratio: 5, shot: "1-04" },
  },
];

const UPDATED = "2026-10-14T11:55:00+08:00";

export const summary: Record<MetricsScope, MetricsSummary> = {
  episode: {
    scope: "episode",
    spent_usd: 8.94,
    budget_usd: 15,
    projected_usd: 13.35,
    insights,
    updated_at: UPDATED,
  },
  series: {
    scope: "series",
    spent_usd: 8.94,
    budget_usd: 45,
    projected_usd: 28.05,
    insights,
    updated_at: UPDATED,
  },
};

const episodeKpis: MetricsKpis = {
  scope: "episode",
  adopted_seconds: 10,
  total_seconds: 34,
  shots: 9,
  shots_adopted: 3,
  cost_per_second_usd: 0.89,
  projected_cost_per_second_usd: 0.39,
  local_gpu_seconds: 2 * 3600 + 12 * 60,
  api_wait_seconds: 44 * 60,
  vram_peak_gb: 29.6,
  api_calls: 42,
  api_succeeded: 41,
  api_canceled: 0,
  rate_limit_retries: 1,
  qa_passed: 6,
  qa_total: 10,
  auto_reruns: 1,
  auto_fallbacks: 1,
  manual_switches: 1,
  adopt_median_seconds: 19 * 60,
  slowest_open: { shot: "1-04", seconds: 38 * 60 },
};

/** Only episode 1 has run, so the series totals are episode 1's (prototype scope note). */
export const kpis: Record<MetricsScope, MetricsKpis> = {
  episode: episodeKpis,
  series: { ...episodeKpis, scope: "series", total_seconds: 184, shots: 9 },
};

const item = (code: string, params: Message["params"] = {}): Message => ({ code, params });

/**
 * Episode 1's ten 15-minute buckets, 09:30–11:55 (prototype `B`): calls by kind, failures and
 * what the money went on.
 */
const BUCKETS: {
  text: number;
  image: number;
  av: number;
  add: number;
  failed?: number;
  items: Message[];
}[] = [
  { text: 0, image: 0, av: 0, add: 0, items: [item("local_draft", { component: "enrich" })] },
  {
    text: 2,
    image: 0,
    av: 0,
    add: 0.03,
    items: [
      item("components_model", {
        component: "enrich",
        component2: "extract",
        model: "DeepSeek V4 Pro",
      }),
    ],
  },
  {
    text: 3,
    image: 0,
    av: 0,
    add: 0.04,
    items: [
      item("component_model", { component: "split", model: "V4.1 Flash" }),
      item("component_model", { component: "script", model: "V4 Pro" }),
    ],
  },
  {
    text: 4,
    image: 0,
    av: 0,
    add: 0.05,
    items: [
      item("switched", { component: "script", model: "Kimi K2.6" }),
      item("component", { component: "plan" }),
    ],
  },
  {
    text: 2,
    image: 6,
    av: 3,
    add: 3.89,
    items: [
      item("voice_design", { cost: 3.02 }),
      item("images_cost", { component: "img", n: 6, cost: 0.84 }),
      item("text_cost", { cost: 0.03 }),
    ],
  },
  {
    text: 2,
    image: 5,
    av: 1,
    add: 1.29,
    items: [
      item("images_cost", { component: "text", n: 4, cost: 1.12 }),
      item("images_cost", { component: "img", n: 1, cost: 0.14 }),
      item("preview_cost", { cost: 0.01 }),
    ],
  },
  {
    text: 1,
    image: 4,
    av: 2,
    add: 1.14,
    items: [
      item("images_cost", { component: "kf", n: 4, cost: 0.56 }),
      item("videos_cost", { from: "1-01", to: "1-02", cost: 0.56 }),
    ],
  },
  {
    text: 0,
    image: 2,
    av: 1,
    add: 0.52,
    items: [
      item("images_cost", { component: "kf", n: 2, cost: 0.28 }),
      item("video_cost", { shot: "1-03", cost: 0.24 }),
    ],
  },
  {
    text: 1,
    image: 0,
    av: 2,
    add: 0.33,
    failed: 1,
    items: [
      item("fallback", { shot: "1-04", model: "H3 API", cost: 0.32 }),
      item("rate_limited", { n: 1 }),
    ],
  },
  {
    text: 0,
    image: 0,
    av: 1,
    add: 1.65,
    items: [item("switch_take", { shot: "1-04", model: "Seedance 2.5", take: "T4", cost: 1.64 })],
  },
];

const DAY = "2026-10-14";
const clock = (minutes: number) => {
  const m = 9 * 60 + 30 + minutes;
  return `${DAY}T${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}:00+08:00`;
};
/** "Now" is 11:55, 145 minutes after 09:30; the axis runs to 14:00. */
const NOW_MIN = 145;
const END_MIN = 270;
const bucketStart = (i: number) => clock(i * 15);
const bucketEnd = (i: number) => clock(Math.min((i + 1) * 15, NOW_MIN));

const round2 = (v: number) => Math.round(v * 100) / 100;

function spendSeries(scope: MetricsScope): SpendSeries {
  let cum = 0;
  return {
    scope,
    bucket_minutes: 15,
    start: clock(0),
    now: clock(NOW_MIN),
    end: clock(END_MIN),
    buckets: BUCKETS.map((b, i) => {
      cum = round2(cum + b.add);
      return {
        start: bucketStart(i),
        end: bucketEnd(i),
        add_usd: b.add,
        cum_usd: cum,
        items: b.items,
      };
    }),
    projected_usd: summary[scope].projected_usd,
    budget_usd: summary[scope].budget_usd,
  };
}

/** Per-kind totals (prototype legend): text 15 · $0.20, image 17 · $2.94, av 10 · $5.80. */
function callsSeries(scope: MetricsScope): CallsSeries {
  return {
    scope,
    bucket_minutes: 15,
    buckets: BUCKETS.map((b, i) => ({
      start: bucketStart(i),
      end: bucketEnd(i),
      counts: { text: b.text, image: b.image, av: b.av },
      failed: b.failed ?? 0,
      cost_usd: b.add,
    })),
    totals: [
      { kind: "text", calls: 15, cost_usd: 0.2 },
      { kind: "image", calls: 17, cost_usd: 2.94 },
      { kind: "av", calls: 10, cost_usd: 5.8 },
    ],
    calls: 42,
    succeeded: 41,
  };
}

export const spend: Record<MetricsScope, SpendSeries> = {
  episode: spendSeries("episode"),
  series: spendSeries("series"),
};

export const calls: Record<MetricsScope, CallsSeries> = {
  episode: callsSeries("episode"),
  series: callsSeries("series"),
};
