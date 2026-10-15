/** Dashboard series (SPEC 11.1). `useMetricsSummary` lives in `series.ts` (the top bar uses it). */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { z } from "zod";

import { api } from "@/api/client";
import {
  CallsSeriesSchema,
  MetricsKpisSchema,
  SpendSeriesSchema,
  type MetricsScope,
} from "@/api/schemas/metrics";

const enc = encodeURIComponent;

type Series = "kpis" | "spend-series" | "calls-series";

export const metricsKeys = {
  series: (name: Series, scope: MetricsScope, id: string) => ["metrics", name, scope, id] as const,
};

/**
 * `id` is the episode id (scope `episode`) or the series id (scope `series`). Switching scope
 * keeps the previous numbers on screen until the new ones arrive (no skeleton flash).
 */
function useMetrics<S extends z.ZodType>(
  name: Series,
  schema: S,
  scope: MetricsScope,
  id: string | undefined,
) {
  return useQuery({
    queryKey: metricsKeys.series(name, scope, id ?? ""),
    queryFn: () => api(`/metrics/${name}?scope=${scope}&${scope}=${enc(id ?? "")}`, schema),
    enabled: !!id,
    placeholderData: keepPreviousData,
  });
}

export const useMetricsKpis = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("kpis", MetricsKpisSchema, scope, id);

export const useSpendSeries = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("spend-series", SpendSeriesSchema, scope, id);

export const useCallsSeries = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("calls-series", CallsSeriesSchema, scope, id);
