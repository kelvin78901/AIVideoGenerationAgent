import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, del, post, put } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { useHealth } from "@/api/hooks/useJobs";
import {
  ComponentCatalogSchema,
  ConfigDefaultsSchema,
  type ConfigDefaults,
  ResolvedConfigSchema,
  type ComponentCatalog,
  type OverrideRequest,
  type ResolvedConfig,
} from "@/api/schemas/config";
import type { ModelOption } from "@/api/schemas/models";
import { ProviderSchema, ProvidersSchema } from "@/api/schemas/providers";

export const configKeys = {
  catalog: ["config", "components"] as const,
  resolved: (component: string, item: string | null) =>
    ["config", "resolve", component, item ?? ""] as const,
  all: ["config"] as const,
  resolvedAll: ["config", "resolve"] as const,
  defaults: ["config", "defaults"] as const,
  providers: ["providers"] as const,
};

const enc = encodeURIComponent;

export function useComponentCatalog() {
  return useQuery({
    queryKey: configKeys.catalog,
    queryFn: () => api("/config/components", ComponentCatalogSchema),
    staleTime: 5 * 60_000,
  });
}

export function useResolvedConfig(component: string | undefined, item: string | null = null) {
  const q = new URLSearchParams({ component: component ?? "" });
  if (item) q.set("item", item);
  return useQuery({
    queryKey: configKeys.resolved(component ?? "", item),
    queryFn: () => api(`/config/resolve?${q.toString()}`, ResolvedConfigSchema),
    enabled: !!component,
  });
}

/** Component-level configs of many components at once (the Models page table). */
export function useResolvedConfigs(components: readonly string[]) {
  return useQueries({
    queries: components.map((component) => ({
      queryKey: configKeys.resolved(component, null),
      queryFn: () => api(`/config/resolve?component=${enc(component)}`, ResolvedConfigSchema),
    })),
  });
}

/** The active preset and fallback policy (`GET /config/defaults`). */
export function useConfigDefaults() {
  return useQuery({
    queryKey: configKeys.defaults,
    queryFn: () => api("/config/defaults", ConfigDefaultsSchema),
  });
}

/** A new preset re-resolves every component that has not been changed by hand. */
export function useSetConfigDefaults() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<ConfigDefaults>) =>
      put("/config/defaults", ConfigDefaultsSchema, patch),
    onSuccess: (defaults) => {
      client.setQueryData(configKeys.defaults, defaults);
      void client.invalidateQueries({ queryKey: configKeys.resolvedAll });
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

/** 「恢复成预设」: drops the component's override so it follows the preset again. */
export function useResetOverride(component: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      del(`/config/override?scope=component&component_id=${enc(component)}`, ResolvedConfigSchema),
    onSuccess: (resolved) => {
      client.setQueryData(configKeys.resolved(component, null), resolved);
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

/** Writes an override and re-resolves; product estimates follow the new route. */
export function useSetOverride(component: string, item: string | null = null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: OverrideRequest["data"]) =>
      put("/config/override", ResolvedConfigSchema, {
        scope: item ? "item" : "component",
        scope_id: item,
        component_id: component,
        data,
      } satisfies OverrideRequest),
    onSuccess: (resolved) => {
      client.setQueryData(configKeys.resolved(component, item), resolved);
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

/** Writing-model providers from the real backend (M0): which keys are set. */
export function useProviders() {
  return useQuery({
    queryKey: configKeys.providers,
    queryFn: () => api("/providers", ProvidersSchema),
  });
}

/** Model keys whose provider needs a key that is not set. Empty in Mock mode (no key needed). */
export function useMissingKeys(): ReadonlySet<string> {
  const health = useHealth();
  const providers = useProviders();
  if (health.data?.mock !== false || !providers.data) return new Set();
  return new Set(
    providers.data.providers
      .filter((p) => p.needs_key && !p.has_key)
      .flatMap((p) => p.models.map((m) => m.key)),
  );
}

/** A component's models: `alt_order` first (the switch menu order), then the rest. */
export function componentModels(
  catalog: ComponentCatalog | undefined,
  component: string,
  resolved?: ResolvedConfig,
): ModelOption[] {
  const def = catalog?.components.find((c) => c.id === component);
  if (!catalog || !def) return [];
  const keys = [...def.local_models, ...def.api_models];
  const order = resolved?.values.alt_order ?? [];
  const rank = (k: string) =>
    order.includes(k) ? order.indexOf(k) : order.length + keys.indexOf(k);
  return keys
    .slice()
    .sort((a, b) => rank(a) - rank(b))
    .flatMap((k) => catalog.models.find((m) => m.key === k) ?? []);
}

/** Models of one component, ready for RunBar / ModelSwitchMenu. */
export function useComponentModels(component: string, item: string | null = null): ModelOption[] {
  const catalog = useComponentCatalog();
  const resolved = useResolvedConfig(component, item);
  return componentModels(catalog.data, component, resolved.data);
}

function useProviderMutation<V>(fn: (vars: V) => Promise<z.infer<typeof ProviderSchema>>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void client.invalidateQueries({ queryKey: configKeys.providers }),
  });
}

/** Keys are write-only: the response only says whether one is set (M0 `/providers`). */
export const useSaveProviderKey = (id: string) =>
  useProviderMutation((apiKey: string) =>
    post(`/providers/${enc(id)}/key`, ProviderSchema, { api_key: apiKey }),
  );

export const useDeleteProviderKey = (id: string) =>
  useProviderMutation(() => del(`/providers/${enc(id)}/key`, ProviderSchema));

export const ProviderTestSchema = z.object({
  ok: z.boolean(),
  detail: z.string().nullable(),
  models: z.array(z.string()),
  media: z
    .array(
      z.object({
        key: z.string(),
        display: z.string(),
        ok: z.boolean(),
        detail: z.string().nullable(),
      }),
    )
    .default([]),
});

/** 「测试连接」: lists the provider's models with the stored key, then checks each media model
 * on that key (free calls, nothing is generated). */
export const useTestProvider = (id: string) =>
  useMutation({ mutationFn: () => post(`/providers/${enc(id)}/test`, ProviderTestSchema) });
