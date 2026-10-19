/**
 * In-memory demo store, built from the fixtures. Handlers read and mutate it; a page reload
 * (or `resetDb()` in tests) brings back the initial demo state.
 */
import type { ComponentConfig, ConfigDefaults } from "@/api/schemas/config";
import type { GateDecision } from "@/api/schemas/gates";
import type { GenerateLogEntry, GenerateRules } from "@/api/schemas/generate";
import type { Impact } from "@/api/schemas/impact";
import type { SyncRun } from "@/api/schemas/sync";
import { componentDefs } from "@/mocks/fixtures/demo/config";
import { assetProducts, assets } from "@/mocks/fixtures/demo/assets";
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
import { bible, novel, suggestions } from "@/mocks/fixtures/demo/novel";
import { scripts } from "@/mocks/fixtures/demo/script";
import { shotProducts, shots } from "@/mocks/fixtures/demo/shots";
import { series } from "@/mocks/fixtures/demo/series";
import { audio, postProducts, subtitles, type ClipSettings } from "@/mocks/fixtures/demo/post";
import { products } from "@/mocks/fixtures/demo/products";
import { syncLog, syncRules, syncTargets } from "@/mocks/fixtures/demo/sync";
import { generateLog, generateRules, takeProducts } from "@/mocks/fixtures/demo/takes";
import { comfyWorkflowFiles, workflows } from "@/mocks/fixtures/demo/workflows";

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
    products: Object.fromEntries(
      [...products, ...assetProducts, ...shotProducts, ...takeProducts, ...postProducts].map(
        (p) => [p.id, p],
      ),
    ),
    assets,
    config: {
      components: componentDefs,
      /** Active preset (its layer is computed, `presetConfig()`) and the fallback policy. */
      defaults: { preset: "balanced", fallback_notify: "after" } as ConfigDefaults,
      project: {} as Partial<ComponentConfig>,
      component: {} as Record<string, Partial<ComponentConfig>>,
      /** `<component>|<item>` → override. */
      item: {} as Record<string, Partial<ComponentConfig>>,
    },
    novel,
    suggestions,
    bible,
    scripts,
    shots,
    generateRules: { [series.id]: generateRules } as Record<string, GenerateRules>,
    generateLog: { [EP1]: generateLog } as Record<string, GenerateLogEntry[]>,
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
    impacts: new Map<string, Impact>(),
    gates: [] as GateDecision[],
    /** Workflow library (SPEC 6.4) and ComfyUI's own workflow list. */
    workflows,
    comfyWorkflowFiles,
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
