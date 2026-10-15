import { http, HttpResponse } from "msw";

import type { CallKind, MetricsScope } from "@/api/schemas/metrics";
import { CALL_KINDS } from "@/api/schemas/metrics";
import { getDb } from "@/mocks/db";
import { CSV_HEADER } from "@/mocks/fixtures/demo/metricsDetail";
import { demoJson, v1 } from "@/mocks/http";
import { DEMO_HEADER } from "@/stores/demo";

/** `?scope=episode&episode=<id>` | `?scope=series&series=<id>`; the demo has one running episode. */
const scopeOf = (request: Request): MetricsScope =>
  new URL(request.url).searchParams.get("scope") === "series" ? "series" : "episode";

/** The detail series only have episode 1's data, so both scopes return the same rows. */
const detail = <K extends keyof ReturnType<typeof getDb>["metrics"]>(path: string, key: K) =>
  http.get(v1(`/metrics/${path}`), () => demoJson(getDb().metrics[key]));

export const metricsHandlers = [
  http.get(v1("/metrics/summary"), ({ request }) => demoJson(getDb().summary[scopeOf(request)])),
  http.get(v1("/metrics/kpis"), ({ request }) => demoJson(getDb().metrics.kpis[scopeOf(request)])),
  http.get(v1("/metrics/spend-series"), ({ request }) =>
    demoJson(getDb().metrics.spend[scopeOf(request)]),
  ),
  http.get(v1("/metrics/calls-series"), ({ request }) =>
    demoJson(getDb().metrics.calls[scopeOf(request)]),
  ),
  detail("shots", "shots"),
  detail("components", "components"),
  detail("speed", "speed"),
  detail("apis", "apis"),
  detail("local-models", "localModels"),
  detail("qa", "qa"),
  detail("episodes", "episodes"),
  http.get(v1("/metrics/export.csv"), () =>
    HttpResponse.text(exportCsv(), {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="calls.csv"',
        [DEMO_HEADER]: "1",
      },
    }),
  ),
];

/**
 * One row per API call: each 15-minute bucket's calls by kind are dealt out to that kind's
 * models in order, so the totals agree with the API table (42 calls, $8.94).
 */
function exportCsv(): string {
  const { calls, apis } = getDb().metrics;
  const left = new Map(apis.rows.map((r) => [r.model, r.calls]));
  const pick = (kind: CallKind) =>
    apis.rows.find((r) => r.kind === kind && (left.get(r.model) ?? 0) > 0);
  const rows: string[][] = [];
  for (const b of calls.episode.buckets) {
    let minute = 0;
    let failed = b.failed;
    for (const kind of CALL_KINDS) {
      for (let i = 0; i < b.counts[kind]; i++) {
        const api = pick(kind);
        if (!api) continue;
        left.set(api.model, (left.get(api.model) ?? 0) - 1);
        const at = new Date(new Date(b.start).getTime() + minute++ * 60000);
        const fail = failed > 0 && api.succeeded < api.calls;
        if (fail) failed--;
        rows.push([
          at.toISOString(),
          kind,
          "",
          api.model,
          "api",
          String(api.median_latency_s),
          api.usage.code,
          (api.cost_usd / api.calls).toFixed(4),
          fail ? "rate_limited" : "success",
        ]);
      }
    }
  }
  const quote = (v: string) => (/[",\n]/.test(v) ? `"${v.replaceAll('"', '""')}"` : v);
  return [CSV_HEADER.join(","), ...rows.map((r) => r.map(quote).join(","))].join("\n") + "\n";
}
