import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { z } from "zod";

import { api, patch, post, put } from "@/api/client";
import {
  EpisodeProgressSchema,
  EpisodeSchema,
  type Episode,
  type EpisodePatch,
} from "@/api/schemas/episodes";
import { MetricsSummarySchema, type MetricsScope } from "@/api/schemas/metrics";
import { SeriesSchema, type SeriesCreate } from "@/api/schemas/series";
import {
  CompatSchema,
  OutputSpecSchema,
  SpecPresetsSchema,
  type Aspect,
  type SpecPatch,
} from "@/api/schemas/spec";
import { DEMO_EPISODE, DEMO_SERIES } from "@/app/paths";
import { useUiStore } from "@/stores/ui";

const enc = encodeURIComponent;

export const seriesKeys = {
  list: ["series-list"] as const,
  detail: (id: string) => ["series", id] as const,
  episodes: (id: string) => ["series", id, "episodes"] as const,
  spec: (id: string) => ["series", id, "spec"] as const,
  compat: (id: string, aspect: string) => ["series", id, "spec", "compat", aspect] as const,
  presets: ["spec", "presets"] as const,
  progress: (episodeId: string) => ["episodes", episodeId, "progress"] as const,
  summary: (scope: MetricsScope, id: string) => ["metrics", "summary", scope, id] as const,
};

/** Newest first (the top bar's series menu). */
export function useSeriesList() {
  return useQuery({
    queryKey: seriesKeys.list,
    queryFn: () => api("/series", z.array(SeriesSchema)),
  });
}

/** `POST /series`: a new series with the default output spec. */
export function useCreateSeries() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SeriesCreate) => post("/series", SeriesSchema, body),
    onSuccess: (created) => {
      client.setQueryData(seriesKeys.detail(created.id), created);
      void client.invalidateQueries({ queryKey: seriesKeys.list });
    },
  });
}

/** The route's series, else the one opened last, else the demo series. */
export function useSeriesId(): string {
  const params = useParams();
  const last = useUiStore((s) => s.lastSeries);
  return params.series ?? last ?? DEMO_SERIES;
}

export function useSeries(id: string) {
  return useQuery({
    queryKey: seriesKeys.detail(id),
    queryFn: () => api(`/series/${enc(id)}`, SeriesSchema),
  });
}

export function useEpisodes(seriesId: string) {
  return useQuery({
    queryKey: seriesKeys.episodes(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/episodes`, z.array(EpisodeSchema)),
  });
}

/** The route's series and episode: `/s/:series/e/:ep` (else `useSeriesId()`, episode 1). */
export function useRouteEpisode(): {
  seriesId: string;
  episodeIdx: number;
  episode: Episode | undefined;
  isLoading: boolean;
} {
  const params = useParams();
  const seriesId = useSeriesId();
  const episodeIdx = Number(params.ep ?? DEMO_EPISODE);
  const episodes = useEpisodes(seriesId);
  return {
    seriesId,
    episodeIdx,
    episode: episodes.data?.find((e) => e.idx === episodeIdx),
    isLoading: episodes.isLoading,
  };
}

export function useEpisodeProgress(episodeId: string | undefined) {
  return useQuery({
    queryKey: seriesKeys.progress(episodeId ?? ""),
    queryFn: () => api(`/episodes/${enc(episodeId ?? "")}/progress`, EpisodeProgressSchema),
    enabled: !!episodeId,
  });
}

export function useOutputSpec(seriesId: string) {
  return useQuery({
    queryKey: seriesKeys.spec(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/spec`, OutputSpecSchema),
  });
}

/** Spend / budget / projection (SPEC 11.1). `id` is the episode id or the series id. */
export function useMetricsSummary(scope: MetricsScope, id: string | undefined) {
  return useQuery({
    queryKey: seriesKeys.summary(scope, id ?? ""),
    queryFn: () =>
      api(`/metrics/summary?scope=${scope}&${scope}=${enc(id ?? "")}`, MetricsSummarySchema),
    enabled: !!id,
  });
}

/** Platform presets and the sizes of every aspect (SPEC 13.1). */
export function useSpecPresets() {
  return useQuery({
    queryKey: seriesKeys.presets,
    queryFn: () => api("/spec/presets", SpecPresetsSchema),
    staleTime: Infinity,
  });
}

/** Which models on the current route make `aspect` natively (SPEC 13.3). */
export function useSpecCompat(seriesId: string, aspect: Aspect | undefined) {
  return useQuery({
    queryKey: seriesKeys.compat(seriesId, aspect ?? ""),
    queryFn: () =>
      api(`/series/${enc(seriesId)}/spec/compat?aspect=${enc(aspect ?? "")}`, CompatSchema),
    enabled: !!aspect,
  });
}

export function useSaveSpec(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: SpecPatch) => put(`/series/${enc(seriesId)}/spec`, OutputSpecSchema, patch),
    onSuccess: (spec) => client.setQueryData(seriesKeys.spec(seriesId), spec),
  });
}

/** `PATCH /episodes/{id}` (the budget, from the Models page); the top bar follows. */
export function useUpdateEpisode(episodeId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: EpisodePatch) =>
      patch(`/episodes/${enc(episodeId ?? "")}`, EpisodeSchema, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["series"] });
      void client.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}
