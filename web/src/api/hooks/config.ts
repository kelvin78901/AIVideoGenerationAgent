import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, put } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { useHealth } from "@/api/hooks/useJobs";
import {
  ComponentCatalogSchema,
  ResolvedConfigSchema,
  type ComponentCatalog,
  type OverrideRequest,
  type ResolvedConfig,
} from "@/api/schemas/config";
import type { ModelOption } from "@/api/schemas/models";
import { ProvidersSchema } from "@/api/schemas/providers";

export const configKeys = {
  catalog: ["config", "components"] as const,
  resolved: (component: string, item: string | null) =>
    ["config", "resolve", component, item ?? ""] as const,
  all: ["config"] as const,
  providers: ["providers"] as const,
};

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
