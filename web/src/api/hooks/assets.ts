import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, patch, post } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { seriesKeys } from "@/api/hooks/series";
import {
  AnalyzeResultSchema,
  AssetSchema,
  type Asset,
  type AssetPatch,
} from "@/api/schemas/assets";

const enc = encodeURIComponent;

export const assetKeys = {
  list: (series: string) => ["series", series, "assets"] as const,
};

export function useAssets(seriesId: string) {
  return useQuery({
    queryKey: assetKeys.list(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/assets`, z.array(AssetSchema)),
  });
}

function useStoreAsset(seriesId: string) {
  const client = useQueryClient();
  return (asset: Asset) =>
    client.setQueryData<Asset[]>(assetKeys.list(seriesId), (old) =>
      old?.map((a) => (a.id === asset.id ? asset : a)),
    );
}

/** Description, picked candidate, on-screen text settings, voice source. */
export function usePatchAsset(seriesId: string) {
  const store = useStoreAsset(seriesId);
  const client = useQueryClient();
  return useMutation({
    mutationFn: (p: { id: string; patch: AssetPatch }) =>
      patch(`/assets/${enc(p.id)}`, AssetSchema, p.patch),
    onSuccess: (asset, p) => {
      store(asset);
      if (p.patch.intent !== undefined)
        void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

/** 锁定为参考 (unlocking goes through the impact preview, kind `asset_unlock`). */
export function useLockAsset(seriesId: string, episodeId: string | undefined) {
  const store = useStoreAsset(seriesId);
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post(`/assets/${enc(id)}/lock`, AssetSchema),
    onSuccess: (asset) => {
      store(asset);
      void client.invalidateQueries({ queryKey: productKeys.all });
      if (episodeId) void client.invalidateQueries({ queryKey: seriesKeys.progress(episodeId) });
    },
  });
}

export function useAnalyzeAssets(episodeId: string | undefined) {
  return useMutation({
    mutationFn: () => post(`/episodes/${enc(episodeId ?? "")}/assets/analyze`, AnalyzeResultSchema),
  });
}
