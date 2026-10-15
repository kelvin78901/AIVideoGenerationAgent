/**
 * In-memory demo store, built from the fixtures. Handlers read and mutate it; a page reload
 * (or `resetDb()` in tests) brings back the initial demo state.
 */
import { episodes, progress } from "@/mocks/fixtures/demo/episodes";
import { summary } from "@/mocks/fixtures/demo/metrics";
import { series } from "@/mocks/fixtures/demo/series";
import { profile } from "@/mocks/fixtures/demo/setup";
import { spec } from "@/mocks/fixtures/demo/spec";

function createDb() {
  return structuredClone({
    series: { [series.id]: series },
    episodes,
    progress,
    specs: { [spec.series_id]: spec },
    summary,
    profile,
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
