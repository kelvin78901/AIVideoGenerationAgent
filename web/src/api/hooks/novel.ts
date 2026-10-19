import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, patch, post, postForm } from "@/api/client";
import {
  BibleEntitySchema,
  BibleSchema,
  NovelImportSchema,
  NovelSchema,
  SuggestionSchema,
  SuggestionsSchema,
  type BibleMergeRequest,
  type BiblePatch,
  type Suggestions,
} from "@/api/schemas/novel";
import { productKeys } from "@/api/hooks/products";

const enc = encodeURIComponent;

export const novelKeys = {
  /** Every chapter of a series' novel (invalidate this after an import). */
  novelAll: (series: string) => ["series", series, "novel"] as const,
  novel: (series: string, chapter: number) => ["series", series, "novel", chapter] as const,
  suggestions: (series: string) => ["series", series, "suggestions"] as const,
  bible: (series: string) => ["series", series, "bible"] as const,
};

/** The novel in use and the paragraphs of one chapter (0-based). */
export function useNovel(seriesId: string, chapter = 0) {
  return useQuery({
    queryKey: novelKeys.novel(seriesId, chapter),
    queryFn: () => api(`/series/${enc(seriesId)}/novel?chapter=${chapter}`, NovelSchema),
    // Switching chapters keeps the current one on screen until the next arrives.
    placeholderData: (prev) => (prev?.series_id === seriesId ? prev : undefined),
  });
}

export interface ImportRequest {
  file: File;
  /** Only report what was found (the preview); nothing is stored. */
  dryRun: boolean;
  rightsConfirmed?: boolean;
}

/** `POST /series/{id}/novel`: preview (`dryRun`) or import; an import refreshes the novel. */
export function useImportNovel(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, dryRun, rightsConfirmed = false }: ImportRequest) => {
      const form = new FormData();
      form.append("file", file);
      form.append("dry_run", String(dryRun));
      form.append("rights_confirmed", String(rightsConfirmed));
      return postForm(`/series/${enc(seriesId)}/novel`, NovelImportSchema, form);
    },
    onSuccess: (result) => {
      if (result.dry_run) return;
      void client.invalidateQueries({ queryKey: novelKeys.novelAll(seriesId) });
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

export function useSuggestions(seriesId: string) {
  return useQuery({
    queryKey: novelKeys.suggestions(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/suggestions`, SuggestionsSchema),
  });
}

export function useBible(seriesId: string) {
  return useQuery({
    queryKey: novelKeys.bible(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/bible`, BibleSchema),
  });
}

/**
 * Edits make an adopted `edit` version of 设定提取, so the bible and the product (history,
 * status) are refetched.
 */
function useBibleRefresh(seriesId: string) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: novelKeys.bible(seriesId) });
    void client.invalidateQueries({ queryKey: productKeys.all });
  };
}

/** 改名、别名、简介、冻结. */
export function useEditBibleEntity(seriesId: string) {
  const refresh = useBibleRefresh(seriesId);
  return useMutation({
    mutationFn: ({ id, ...body }: BiblePatch & { id: string }) =>
      patch(`/bible/${enc(id)}`, BibleEntitySchema, body),
    onSuccess: refresh,
  });
}

/** 确认合并 / 不是同一个 / 拆分. */
export function useMergeBible(seriesId: string) {
  const client = useQueryClient();
  const refresh = useBibleRefresh(seriesId);
  return useMutation({
    mutationFn: (body: BibleMergeRequest) => post("/bible/merge", BibleSchema, body),
    onSuccess: (bible) => {
      client.setQueryData(novelKeys.bible(seriesId), bible);
      refresh();
    },
  });
}

export type SuggestionAction =
  | { id: string; action: "accept" | "reject" | "reset" }
  /** `confirm_budget` after a 409 `over_budget` (the user agreed to the estimate). */
  | { id: string; action: "rewrite"; instruction: string; confirm_budget?: boolean };

/**
 * 采纳 / 撤销采纳 / 忽略 / 恢复 / 按要求重写: one suggestion, updated in the cached list. What the
 * bible reads changes with it (it may turn 待更新), so products are refetched too.
 */
export function useSuggestionAction(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (a: SuggestionAction) =>
      post(
        `/suggestions/${enc(a.id)}/${a.action}`,
        SuggestionSchema,
        a.action === "rewrite"
          ? { instruction: a.instruction, confirm_budget: a.confirm_budget ?? false }
          : undefined,
      ),
    onSuccess: (updated) => {
      client.setQueryData<Suggestions>(novelKeys.suggestions(seriesId), (old) =>
        old
          ? { ...old, suggestions: old.suggestions.map((s) => (s.id === updated.id ? updated : s)) }
          : old,
      );
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

export function useAcceptAllSuggestions(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => post(`/series/${enc(seriesId)}/suggestions/accept-all`, SuggestionsSchema),
    onSuccess: (data) => {
      client.setQueryData(novelKeys.suggestions(seriesId), data);
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}
