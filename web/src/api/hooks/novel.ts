import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, post } from "@/api/client";
import {
  BibleEntitySchema,
  NovelSchema,
  SuggestionSchema,
  type Suggestion,
} from "@/api/schemas/novel";

const enc = encodeURIComponent;

export const novelKeys = {
  novel: (series: string) => ["series", series, "novel"] as const,
  suggestions: (series: string) => ["series", series, "suggestions"] as const,
  bible: (series: string) => ["series", series, "bible"] as const,
};

export function useNovel(seriesId: string) {
  return useQuery({
    queryKey: novelKeys.novel(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/novel`, NovelSchema),
  });
}

export function useSuggestions(seriesId: string) {
  return useQuery({
    queryKey: novelKeys.suggestions(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/suggestions`, z.array(SuggestionSchema)),
  });
}

export function useBible(seriesId: string) {
  return useQuery({
    queryKey: novelKeys.bible(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/bible`, z.array(BibleEntitySchema)),
  });
}

export type SuggestionAction =
  | { id: string; action: "accept" | "reject" | "reset" }
  | { id: string; action: "rewrite"; instruction: string };

/** 采纳 / 撤销采纳 / 忽略 / 恢复 / 按要求重写: one suggestion, updated in the cached list. */
export function useSuggestionAction(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (a: SuggestionAction) =>
      post(
        `/suggestions/${enc(a.id)}/${a.action}`,
        SuggestionSchema,
        a.action === "rewrite" ? { instruction: a.instruction } : undefined,
      ),
    onSuccess: (updated) =>
      client.setQueryData<Suggestion[]>(novelKeys.suggestions(seriesId), (old) =>
        old?.map((s) => (s.id === updated.id ? updated : s)),
      ),
  });
}

export function useAcceptAllSuggestions(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      post(`/series/${enc(seriesId)}/suggestions/accept-all`, z.array(SuggestionSchema)),
    onSuccess: (list) => client.setQueryData(novelKeys.suggestions(seriesId), list),
  });
}
