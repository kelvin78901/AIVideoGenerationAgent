import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { z } from "zod";

import { api } from "@/api/client";
import { EpisodeProgressSchema, EpisodeSchema, type Episode } from "@/api/schemas/episodes";
import { MetricsSummarySchema, type MetricsScope } from "@/api/schemas/metrics";
import { SeriesSchema } from "@/api/schemas/series";
import { MachineProfileSchema } from "@/api/schemas/setup";
import { OutputSpecSchema } from "@/api/schemas/spec";
import { DEMO_EPISODE, DEMO_SERIES } from "@/app/paths";

const enc = encodeURIComponent;

export const seriesKeys = {
  detail: (id: string) => ["series", id] as const,
  episodes: (id: string) => ["series", id, "episodes"] as const,
  spec: (id: string) => ["series", id, "spec"] as const,
  progress: (episodeId: string) => ["episodes", episodeId, "progress"] as const,
  summary: (scope: MetricsScope, id: string) => ["metrics", "summary", scope, id] as const,
  profile: ["setup", "profile"] as const,
};

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

/** The route's series and episode: `/s/:series/e/:ep` (falls back to the demo episode). */
export function useRouteEpisode(): {
  seriesId: string;
  episodeIdx: number;
  episode: Episode | undefined;
  isLoading: boolean;
} {
  const params = useParams();
  const seriesId = params.series ?? DEMO_SERIES;
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

export function useMachineProfile() {
  return useQuery({
    queryKey: seriesKeys.profile,
    queryFn: () => api("/setup/profile", MachineProfileSchema),
  });
}
