/**
 * In-memory demo store, built from the fixtures. Handlers read and mutate it; a page reload
 * (or `resetDb()` in tests) brings back the initial demo state.
 */
import type { GateDecision } from "@/api/schemas/gates";
import type { Product } from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";
import type { SyncRun } from "@/api/schemas/sync";
import { assets } from "@/mocks/fixtures/demo/assets";
import { EP1, episodes, progress } from "@/mocks/fixtures/demo/episodes";
import { calls, kpis, spend, summary } from "@/mocks/fixtures/demo/metrics";
import {
  apiMetrics,
  componentMetrics,
  episodeMetrics,
  localModelMetrics,
  qaMetrics,
  shotMetrics,
  speedMetrics,
} from "@/mocks/fixtures/demo/metricsDetail";
import { series } from "@/mocks/fixtures/demo/series";
import { audio, postProducts, subtitles, type ClipSettings } from "@/mocks/fixtures/demo/post";
import { syncLog, syncRules, syncTargets } from "@/mocks/fixtures/demo/sync";
import { finishingProducts } from "@/mocks/fixtures/demo/finishing";

function createDb() {
  return structuredClone({
    series: { [series.id]: series },
    episodes,
    progress,
    summary,
    /** Dashboard series (read-only in the demo). */
    metrics: {
      kpis,
      spend,
      calls,
      shots: shotMetrics,
      components: componentMetrics,
      speed: speedMetrics,
      apis: apiMetrics,
      localModels: localModelMetrics,
      qa: qaMetrics,
      episodes: episodeMetrics,
    },
    products: Object.fromEntries([...finishingProducts, ...postProducts].map((p) => [p.id, p])),
    assets,
    /** Episode 1's shots and video takes as the backend last answered them (`handlers/shots.ts`). */
    shots: [] as Shot[],
    videos: [] as Product[],
    /** Episode 1's post: per-shot clip settings, anchored audio and subtitles. */
    post: {
      episode_id: EP1,
      clips: {} as Record<string, Partial<ClipSettings>>,
      audio,
      subtitles,
    },
    /** Sync settings, the log and the manual run in progress. */
    sync: {
      targets: syncTargets,
      rules: syncRules,
      log: syncLog,
      run: null as SyncRun | null,
      runs: 0,
    },
    gates: [] as GateDecision[],
  });
}

export type DemoDb = ReturnType<typeof createDb>;

let db = createDb();

export function getDb(): DemoDb {
  return db;
}

export function resetDb(): void {
  db = createDb();
}
