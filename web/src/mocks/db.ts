/**
 * In-memory demo store, built from the fixtures. Handlers read and mutate it; a page reload
 * (or `resetDb()` in tests) brings back the initial demo state.
 */
import { series } from "@/mocks/fixtures/demo/series";

function createDb() {
  return structuredClone({
    series: { [series.id]: series },
  });
}

let db = createDb();

export function getDb() {
  return db;
}

export function resetDb(): void {
  db = createDb();
}
