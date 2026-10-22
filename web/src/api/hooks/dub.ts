import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, patch, post } from "@/api/client";
import {
  DubLineSchema,
  DubSchema,
  DubStartSchema,
  type Dub,
  type DubRequest,
} from "@/api/schemas/dub";

const enc = encodeURIComponent;

/** Not under `["episodes"]`: a line's take refreshes these alone (`api/events.ts`). */
export const dubKeys = {
  all: ["dub"] as const,
  episode: (episodeId: string) => ["dub", episodeId] as const,
};

/** 台词配音 of an episode: each spoken line's audio, and the scenes' lengths. */
export function useEpisodeDub(episodeId: string | undefined) {
  return useQuery({
    queryKey: dubKeys.episode(episodeId ?? ""),
    queryFn: () => api(`/episodes/${enc(episodeId ?? "")}/dub`, DubSchema),
    enabled: !!episodeId,
  });
}

/** 「全部配音」 (`dry_run` first for the estimate), or 「配音 / 重配」 of some lines. */
export function useDubEpisode(episodeId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: DubRequest) =>
      post(`/episodes/${enc(episodeId ?? "")}/dub`, DubStartSchema, body),
    onSuccess: (out, body) => {
      if (!body.dry_run && out.jobs.length)
        void client.invalidateQueries({ queryKey: dubKeys.episode(episodeId ?? "") });
    },
  });
}

/** A line's emotion by hand (null: from its tone again); the next take reads with it. */
export function useSetLineEmotion(episodeId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (p: { lineId: string; emotion: string | null }) =>
      patch(`/lines/${enc(p.lineId)}/dub`, DubLineSchema, { emotion: p.emotion }),
    onSuccess: (line) =>
      client.setQueryData<Dub>(dubKeys.episode(episodeId ?? ""), (old) =>
        old
          ? { ...old, lines: old.lines.map((x) => (x.line_id === line.line_id ? line : x)) }
          : old,
      ),
  });
}
