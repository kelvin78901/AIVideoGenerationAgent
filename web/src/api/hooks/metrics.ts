/** Dashboard series (SPEC 11.1). `useMetricsSummary` lives in `series.ts` (the top bar uses it). */
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import type { z } from "zod";

import { api, apiBlob } from "@/api/client";
import {
  ApiMetricsSchema,
  CallsSeriesSchema,
  ComponentMetricsSchema,
  EpisodeMetricsSchema,
  LocalModelMetricsSchema,
  MetricsKpisSchema,
  QaMetricsSchema,
  ShotMetricsSchema,
  SpeedMetricsSchema,
  SpendSeriesSchema,
  type MetricsScope,
} from "@/api/schemas/metrics";

const enc = encodeURIComponent;

type Series =
  | "kpis"
  | "spend-series"
  | "calls-series"
  | "shots"
  | "components"
  | "speed"
  | "apis"
  | "local-models"
  | "qa"
  | "episodes";

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

/** The lower modules; the demo only has episode 1's rows (the scope note says so). */
export const useShotMetrics = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("shots", ShotMetricsSchema, scope, id);
export const useComponentMetrics = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("components", ComponentMetricsSchema, scope, id);
export const useSpeedMetrics = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("speed", SpeedMetricsSchema, scope, id);
export const useApiMetrics = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("apis", ApiMetricsSchema, scope, id);
export const useLocalModelMetrics = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("local-models", LocalModelMetricsSchema, scope, id);
export const useQaMetrics = (scope: MetricsScope, id: string | undefined) =>
  useMetrics("qa", QaMetricsSchema, scope, id);
/** Always the whole series: one row per episode. */
export const useEpisodeMetrics = (seriesId: string) =>
  useMetrics("episodes", EpisodeMetricsSchema, "series", seriesId);

/** Downloads `model_call` rows as `calls.csv` (SPEC 11.1 `/metrics/export.csv`). */
export function useExportCsv() {
  return useMutation({
    mutationFn: async ({ scope, id }: { scope: MetricsScope; id: string }) => {
      const blob = await apiBlob(`/metrics/export.csv?scope=${scope}&${scope}=${enc(id)}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "calls.csv";
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    },
  });
}
