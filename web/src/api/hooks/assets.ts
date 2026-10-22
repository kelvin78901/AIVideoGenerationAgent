import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, patch, post, postForm } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { seriesKeys } from "@/api/hooks/series";
import {
  AssetMatrixSchema,
  AssetSchema,
  type Asset,
  type AssetLock,
  type AssetPatch,
} from "@/api/schemas/assets";
import { JobSchema } from "@/api/schemas/jobs";

const enc = encodeURIComponent;

export const assetKeys = {
  /** Every list of the series (one per episode asked about). */
  all: (series: string) => ["series", series, "assets"] as const,
  list: (series: string, episode: string | undefined) =>
    ["series", series, "assets", episode ?? ""] as const,
  matrix: (episode: string) => ["episodes", episode, "assets", "matrix"] as const,
};

/** The series' assets; `scenes` and `source` are about `episodeId`. */
export function useAssets(seriesId: string, episodeId: string | undefined) {
  const q = episodeId ? `?episode=${enc(episodeId)}` : "";
  return useQuery({
    queryKey: assetKeys.list(seriesId, episodeId),
    queryFn: () => api(`/series/${enc(seriesId)}/assets${q}`, z.array(AssetSchema)),
  });
}

/** 出场矩阵 of an episode. */
export function useAssetMatrix(episodeId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: assetKeys.matrix(episodeId ?? ""),
    queryFn: () => api(`/episodes/${enc(episodeId ?? "")}/assets/matrix`, AssetMatrixSchema),
    enabled: enabled && !!episodeId,
  });
}

/** The asset an edit returned, in every list of the series (the episode only changes
 * `scenes` and `source`, which an edit never touches). */
function useStoreAsset(seriesId: string) {
  const client = useQueryClient();
  return (asset: Asset) =>
    client.setQueriesData<Asset[]>({ queryKey: assetKeys.all(seriesId) }, (old) =>
      old?.map((a) => (a.id === asset.id ? { ...asset, scenes: a.scenes, shots: a.shots } : a)),
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
    mutationFn: (p: { id: string; body?: AssetLock }) =>
      post(`/assets/${enc(p.id)}/lock`, AssetSchema, p.body ?? {}),
    onSuccess: (asset) => {
      store(asset);
      void client.invalidateQueries({ queryKey: productKeys.all });
      if (episodeId) void client.invalidateQueries({ queryKey: seriesKeys.progress(episodeId) });
    },
  });
}

/** 上传参考图: a new version with that one candidate, picked. */
export function useUploadAsset(seriesId: string) {
  const store = useStoreAsset(seriesId);
  const client = useQueryClient();
  return useMutation({
    mutationFn: (p: { id: string; file: File }) => {
      const form = new FormData();
      form.append("file", p.file);
      return postForm(`/assets/${enc(p.id)}/upload`, AssetSchema, form);
    },
    onSuccess: (asset) => {
      store(asset);
      void client.invalidateQueries({ queryKey: productKeys.detail(asset.product_id) });
    },
  });
}

/** 重新分析剧本 → the 素材分析 job; the list refreshes when its version arrives. */
export function useAnalyzeAssets(episodeId: string | undefined) {
  return useMutation({
    mutationFn: () => post(`/episodes/${enc(episodeId ?? "")}/assets/analyze`, JobSchema),
  });
}
