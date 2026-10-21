/**
 * Fake `/config/*` for page tests: the backend's catalog and preset layers
 * (`test/data/config.json`, written by `tests/api/test_web_fixtures.py`) with overrides on top,
 * resolved the way `core/config.py:resolve()` does (preset → project → component → item).
 */
import { http, HttpResponse } from "msw";

import {
  CONFIG_FIELDS,
  ConfigDefaultsSchema,
  OverrideRequestSchema,
  type ComponentCatalog,
  type ComponentConfig,
  type ConfigDefaults,
  type ConfigSource,
  type PresetId,
  type ResolvedConfig,
} from "@/api/schemas/config";
import data from "@/test/data/config.json";

const catalog = data.catalog as ComponentCatalog;
const presets = data.presets as unknown as Record<PresetId, Record<string, ComponentConfig>>;

type Layer = Partial<ComponentConfig>;

/** State of the fake; `resetFakeConfig()` (called by `backend()`) restores it. Tests read it. */
export const fakeConfig = {
  catalog: structuredClone(catalog),
  defaults: { preset: "balanced", fallback_notify: "after" } as ConfigDefaults,
  project: {} as Layer,
  component: {} as Record<string, Layer>,
  /** `<component>|<item>` → override. */
  item: {} as Record<string, Layer>,
};

export function resetFakeConfig() {
  fakeConfig.catalog = structuredClone(catalog);
  fakeConfig.defaults = { preset: "balanced", fallback_notify: "after" };
  fakeConfig.project = {};
  fakeConfig.component = {};
  fakeConfig.item = {};
}

export function fakeResolve(componentId: string, item: string | null): ResolvedConfig | null {
  const base = presets[fakeConfig.defaults.preset][componentId];
  if (!base) return null;
  const values = structuredClone(base);
  values.fallback.notify = fakeConfig.defaults.fallback_notify;
  const sources = Object.fromEntries(CONFIG_FIELDS.map((f) => [f, "preset"])) as Record<
    (typeof CONFIG_FIELDS)[number],
    ConfigSource
  >;
  const layers: [ConfigSource, Layer | undefined][] = [
    ["project", fakeConfig.project],
    ["component", fakeConfig.component[componentId]],
    ["item", item ? fakeConfig.item[`${componentId}|${item}`] : undefined],
  ];
  for (const [source, layer] of layers) {
    for (const field of CONFIG_FIELDS) {
      if (layer?.[field] === undefined) continue;
      (values as Record<string, unknown>)[field] = structuredClone(layer[field]);
      sources[field] = source;
    }
  }
  return { component_id: componentId, item, values, sources };
}

const without = <T>(rec: Record<string, T>, key: string) =>
  Object.fromEntries(Object.entries(rec).filter(([k]) => k !== key));

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

export function configHandlers() {
  return [
    http.get("*/api/v1/config/components", () => HttpResponse.json(fakeConfig.catalog)),
    http.get("*/api/v1/config/resolve", ({ request }) => {
      const q = new URL(request.url).searchParams;
      const component = q.get("component") ?? "";
      const resolved = fakeResolve(component, q.get("item"));
      return resolved
        ? HttpResponse.json(resolved)
        : error(404, "unknown_component", { id: component });
    }),
    http.put("*/api/v1/config/override", async ({ request }) => {
      const body = OverrideRequestSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const { scope, scope_id, component_id, data: patch } = body.data;
      if (!fakeResolve(component_id, null)) return error(404, "unknown_component");
      if (scope === "project") fakeConfig.project = { ...fakeConfig.project, ...patch };
      else if (scope === "component")
        fakeConfig.component[component_id] = { ...fakeConfig.component[component_id], ...patch };
      else {
        if (!scope_id) return error(422, "scope_id_required");
        const key = `${component_id}|${scope_id}`;
        fakeConfig.item[key] = { ...fakeConfig.item[key], ...patch };
      }
      return HttpResponse.json(fakeResolve(component_id, scope === "item" ? scope_id : null));
    }),
    http.delete("*/api/v1/config/override", ({ request }) => {
      const q = new URL(request.url).searchParams;
      const scope = q.get("scope");
      const component = q.get("component_id") ?? "";
      const item = q.get("scope_id");
      if (!fakeResolve(component, null)) return error(404, "unknown_component");
      if (scope === "project") fakeConfig.project = {};
      else if (scope === "component")
        fakeConfig.component = without(fakeConfig.component, component);
      else fakeConfig.item = without(fakeConfig.item, `${component}|${item ?? ""}`);
      return HttpResponse.json(fakeResolve(component, scope === "item" ? item : null));
    }),
    http.get("*/api/v1/config/defaults", () => HttpResponse.json(fakeConfig.defaults)),
    http.put("*/api/v1/config/defaults", async ({ request }) => {
      const body = ConfigDefaultsSchema.partial().safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      fakeConfig.defaults = { ...fakeConfig.defaults, ...body.data };
      return HttpResponse.json(fakeConfig.defaults);
    }),
  ];
}
