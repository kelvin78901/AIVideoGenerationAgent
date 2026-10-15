import { http } from "msw";

import type { MetricsScope } from "@/api/schemas/metrics";
import { getDb } from "@/mocks/db";
import { demoJson, v1 } from "@/mocks/http";

/** `?scope=episode&episode=<id>` | `?scope=series&series=<id>`; the demo has one running episode. */
const scopeOf = (request: Request): MetricsScope =>
  new URL(request.url).searchParams.get("scope") === "series" ? "series" : "episode";

export const metricsHandlers = [
  http.get(v1("/metrics/summary"), ({ request }) => demoJson(getDb().summary[scopeOf(request)])),
  http.get(v1("/metrics/kpis"), ({ request }) => demoJson(getDb().metrics.kpis[scopeOf(request)])),
  http.get(v1("/metrics/spend-series"), ({ request }) =>
    demoJson(getDb().metrics.spend[scopeOf(request)]),
  ),
  http.get(v1("/metrics/calls-series"), ({ request }) =>
    demoJson(getDb().metrics.calls[scopeOf(request)]),
  ),
];
