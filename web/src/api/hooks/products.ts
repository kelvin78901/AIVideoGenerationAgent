import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, post, put } from "@/api/client";
import { JobSchema } from "@/api/schemas/jobs";
import {
  CompileResultSchema,
  ProductSchema,
  type Product,
  type RunRequest,
  type SavePromptRequest,
} from "@/api/schemas/products";

const enc = encodeURIComponent;

export const productKeys = {
  all: ["products"] as const,
  detail: (id: string) => ["products", "detail", id] as const,
  list: (filter: ProductFilter) => ["products", "list", filter] as const,
  compile: (id: string, intent: string, model: string | undefined) =>
    ["products", "compile", id, intent, model ?? ""] as const,
};

export interface ProductFilter {
  /** `<owner_type>:<owner_id>`, e.g. `series:demo`, `shot:1-05`. */
  owner?: string;
  component?: string;
}

export function useProduct(id: string | undefined) {
  return useQuery({
    queryKey: productKeys.detail(id ?? ""),
    queryFn: () => api(`/products/${enc(id ?? "")}`, ProductSchema),
    enabled: !!id,
  });
}

export function useProducts(filter: ProductFilter) {
  const q = new URLSearchParams();
  if (filter.owner) q.set("owner", filter.owner);
  if (filter.component) q.set("component", filter.component);
  return useQuery({
    queryKey: productKeys.list(filter),
    queryFn: () => api(`/products?${q.toString()}`, z.array(ProductSchema)),
  });
}

/** Put a product returned by a mutation into the cache, and refresh lists that contain it. */
function useStoreProduct() {
  const client = useQueryClient();
  return (product: Product) => {
    client.setQueryData(productKeys.detail(product.id), product);
    void client.invalidateQueries({ queryKey: ["products", "list"] });
  };
}

/**
 * 重跑 / 不满意换一个 / 保存并重跑 (SPEC 7.4) → a job. The product turns `running` right away;
 * the new version arrives later with `version.created`.
 */
export function useRunProduct(productId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: RunRequest) => post(`/products/${enc(productId)}/run`, JobSchema, body),
    onSuccess: () => client.invalidateQueries({ queryKey: productKeys.detail(productId) }),
  });
}

export function useSetCurrent() {
  const store = useStoreProduct();
  return useMutation({
    mutationFn: (versionId: string) =>
      post(`/versions/${enc(versionId)}/set-current`, ProductSchema),
    onSuccess: store,
  });
}

/** 采纳这一版: one adopted version per product; downstream steps use it. */
export function useAdopt() {
  const store = useStoreProduct();
  return useMutation({
    mutationFn: (versionId: string) => post(`/versions/${enc(versionId)}/adopt`, ProductSchema),
    onSuccess: store,
  });
}

export function useLock(productId: string) {
  const store = useStoreProduct();
  return useMutation({
    mutationFn: (locked: boolean) =>
      post(`/products/${enc(productId)}/${locked ? "lock" : "unlock"}`, ProductSchema),
    onSuccess: store,
  });
}

/** 只保存: the next run uses this prompt. `compiled: null` = compile from the intent. */
export function useSavePrompt(productId: string) {
  const store = useStoreProduct();
  return useMutation({
    mutationFn: (body: SavePromptRequest) =>
      put(`/products/${enc(productId)}/prompt`, ProductSchema, body),
    onSuccess: store,
  });
}

/** Preview of the compiled layer for an intent (callers debounce the intent). */
export function useCompilePreview(productId: string, intent: string, model?: string) {
  return useQuery({
    queryKey: productKeys.compile(productId, intent, model),
    queryFn: () =>
      post(`/products/${enc(productId)}/compile`, CompileResultSchema, { intent, model }),
    placeholderData: keepPreviousData,
  });
}
