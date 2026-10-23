import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, patch, post } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { seriesKeys } from "@/api/hooks/series";
import { ShotSchema, type Shot, type ShotPatch } from "@/api/schemas/shots";

const enc = encodeURIComponent;

export const shotKeys = {
  list: (episodeId: string) => ["episodes", episodeId, "shots"] as const,
};

export function useShots(episodeId: string | undefined) {
  return useQuery({
    queryKey: shotKeys.list(episodeId ?? ""),
    queryFn: () => api(`/episodes/${enc(episodeId ?? "")}/shots`, z.array(ShotSchema)),
    enabled: !!episodeId,
  });
}

/** An edit appends a 分镜规划 version and confirming locks a keyframe: products and the 分镜
 * badge follow. */
function useAfterEdit(episodeId: string | undefined) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: productKeys.all });
    if (episodeId) void client.invalidateQueries({ queryKey: seriesKeys.progress(episodeId) });
  };
}

/** Any shot setting; the cached list updates at once (blocking drags feel immediate). A
 * duration of null goes back to automatic (worked out by the backend). */
export function usePatchShot(episodeId: string | undefined) {
  const client = useQueryClient();
  const after = useAfterEdit(episodeId);
  const key = shotKeys.list(episodeId ?? "");
  return useMutation({
    mutationFn: (p: { id: string; patch: ShotPatch }) =>
      patch(`/shots/${enc(p.id)}`, ShotSchema, p.patch),
    onMutate: ({ id, patch: change }) => {
      const { duration_s: seconds, ...rest } = change;
      const shown =
        seconds === null || seconds === undefined ? rest : { ...rest, duration_s: seconds };
      client.setQueryData<Shot[]>(key, (old) =>
        old?.map((s) => (s.id === id ? { ...s, ...shown } : s)),
      );
    },
    onSuccess: (shot) => {
      client.setQueryData<Shot[]>(key, (old) => old?.map((s) => (s.id === shot.id ? shot : s)));
      after();
    },
    onError: () => client.invalidateQueries({ queryKey: key }),
  });
}

/** 拆分 (after a line; default the middle) and 和下一个合并: the episode's shots come back. */
export function useSplitShot(episodeId: string | undefined) {
  const client = useQueryClient();
  const after = useAfterEdit(episodeId);
  return useMutation({
    mutationFn: (p: { id: string; afterLineId?: string }) =>
      post(`/shots/${enc(p.id)}/split`, z.array(ShotSchema), {
        after_line_id: p.afterLineId ?? null,
      }),
    onSuccess: (list) => {
      client.setQueryData(shotKeys.list(episodeId ?? ""), list);
      after();
    },
  });
}

export function useMergeShot(episodeId: string | undefined) {
  const client = useQueryClient();
  const after = useAfterEdit(episodeId);
  return useMutation({
    mutationFn: (id: string) => post(`/shots/${enc(id)}/merge`, z.array(ShotSchema), {}),
    onSuccess: (list) => {
      client.setQueryData(shotKeys.list(episodeId ?? ""), list);
      after();
    },
  });
}
