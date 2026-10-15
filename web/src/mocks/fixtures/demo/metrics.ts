/** Dashboard numbers (prototype Dashboard; SPEC 11.2): spent $8.94, projected $13.35, budget $15. */
import type { MetricsSummary } from "@/api/schemas/metrics";

const insights: MetricsSummary["insights"] = [
  { code: "one_off_assets", params: { voice: 3.04, images: 1.68, share: 53 } },
  { code: "slowest_shot", params: { shot: "1-04", minutes: 31 } },
  { code: "pricey_model", params: { model: "Seedance 2.5", price: 0.41, ratio: 5, shot: "1-04" } },
];

export const summary: Record<"episode" | "series", MetricsSummary> = {
  episode: {
    scope: "episode",
    spent_usd: 8.94,
    budget_usd: 15,
    projected_usd: 13.35,
    insights,
    updated_at: "2026-10-14T11:55:00+08:00",
  },
  series: {
    scope: "series",
    spent_usd: 8.94,
    budget_usd: 45,
    projected_usd: 28.05,
    insights,
    updated_at: "2026-10-14T11:55:00+08:00",
  },
};
