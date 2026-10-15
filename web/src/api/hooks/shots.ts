import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, patch } from "@/api/client";
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

/** Any shot setting; the cached list updates at once (blocking drags feel immediate). */
export function usePatchShot(episodeId: string | undefined) {
  const client = useQueryClient();
  const key = shotKeys.list(episodeId ?? "");
  return useMutation({
    mutationFn: (p: { id: string; patch: ShotPatch }) =>
      patch(`/shots/${enc(p.id)}`, ShotSchema, p.patch),
    onMutate: ({ id, patch: change }) =>
      client.setQueryData<Shot[]>(key, (old) =>
        old?.map((s) => (s.id === id ? { ...s, ...change } : s)),
      ),
    onSuccess: (shot, { patch: change }) => {
      client.setQueryData<Shot[]>(key, (old) => old?.map((s) => (s.id === shot.id ? shot : s)));
      if (change.confirmed !== undefined && episodeId) {
        void client.invalidateQueries({ queryKey: seriesKeys.progress(episodeId) });
        void client.invalidateQueries({ queryKey: productKeys.all });
      }
    },
    onError: () => client.invalidateQueries({ queryKey: key }),
  });
}
