import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, del, patch, post, put } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { seriesKeys } from "@/api/hooks/series";
import {
  GenerateLogEntrySchema,
  GenerateRulesSchema,
  WorkflowRulesSchema,
  type GenerateRulesPatch,
  type WorkflowRulesPut,
} from "@/api/schemas/generate";
import { JobSchema } from "@/api/schemas/jobs";
import { ProductSchema, type Product, type VersionPatch } from "@/api/schemas/products";

const enc = encodeURIComponent;

export const generateKeys = {
  rules: (seriesId: string) => ["series", seriesId, "generate-rules"] as const,
  workflowRules: (seriesId: string) => ["series", seriesId, "workflow-rules"] as const,
  logs: ["generate-log"] as const,
  log: (episodeId: string) => ["generate-log", episodeId] as const,
};

export function useGenerateRules(seriesId: string) {
  return useQuery({
    queryKey: generateKeys.rules(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/generate-rules`, GenerateRulesSchema),
  });
}

export function useSaveGenerateRules(seriesId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: GenerateRulesPatch) =>
      put(`/series/${enc(seriesId)}/generate-rules`, GenerateRulesSchema, body),
    onSuccess: (rules) => client.setQueryData(generateKeys.rules(seriesId), rules),
  });
}

/** 按镜头选工作流: the series' rules table (models page). */
export function useWorkflowRules(seriesId: string) {
  return useQuery({
    queryKey: generateKeys.workflowRules(seriesId),
    queryFn: () => api(`/series/${enc(seriesId)}/workflow-rules`, WorkflowRulesSchema),
  });
}

/** Replace the table (`body`), or go back to the config's (`null`). */
export function useSaveWorkflowRules(seriesId: string) {
  const client = useQueryClient();
  const url = `/series/${enc(seriesId)}/workflow-rules`;
  return useMutation({
    mutationFn: (body: WorkflowRulesPut | null) =>
      body ? put(url, WorkflowRulesSchema, body) : del(url, WorkflowRulesSchema),
    onSuccess: (rules) => client.setQueryData(generateKeys.workflowRules(seriesId), rules),
  });
}

/** 运行记录; refreshed whenever a version is created (api/events.ts). */
export function useGenerateLog(episodeId: string | undefined) {
  return useQuery({
    queryKey: generateKeys.log(episodeId ?? ""),
    queryFn: () =>
      api(`/episodes/${enc(episodeId ?? "")}/generate-log`, z.array(GenerateLogEntrySchema)),
    enabled: !!episodeId,
  });
}

/** Adopting or un-adopting a take changes the 生成 n/9 badge and what waits on it. */
function useStoreTake(episodeId: string | undefined) {
  const client = useQueryClient();
  return (product: Product) => {
    client.setQueryData(productKeys.detail(product.id), product);
    void client.invalidateQueries({ queryKey: ["products", "list"] });
    if (episodeId) void client.invalidateQueries({ queryKey: seriesKeys.progress(episodeId) });
  };
}

/** 采纳 a take (one per shot). */
export function useAdoptTake(episodeId: string | undefined) {
  const store = useStoreTake(episodeId);
  return useMutation({
    mutationFn: (versionId: string) => post(`/versions/${enc(versionId)}/adopt`, ProductSchema),
    onSuccess: store,
  });
}

/** 取消采纳 */
export function useUnadopt(episodeId: string | undefined) {
  const store = useStoreTake(episodeId);
  return useMutation({
    mutationFn: (productId: string) => post(`/products/${enc(productId)}/unadopt`, ProductSchema),
    onSuccess: store,
  });
}

/** 数字键打分 */
export function usePatchVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (p: { id: string; patch: VersionPatch }) =>
      patch(`/versions/${enc(p.id)}`, ProductSchema, p.patch),
    onSuccess: (product) => client.setQueryData(productKeys.detail(product.id), product),
  });
}

/** 2K 精修 a take on the finishing component's route → job. */
export function useUpscale() {
  return useMutation({
    mutationFn: (versionId: string) => post(`/versions/${enc(versionId)}/upscale`, JobSchema),
  });
}
