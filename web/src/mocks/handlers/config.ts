import { http } from "msw";

import { z } from "zod";

import {
  CONFIG_FIELDS,
  ConfigDefaultsSchema,
  OverrideRequestSchema,
  type ComponentConfig,
  type ConfigSource,
  type ResolvedConfig,
} from "@/api/schemas/config";
import { getDb } from "@/mocks/db";
import { presetConfig } from "@/mocks/fixtures/demo/config";
import { allModels } from "@/mocks/fixtures/demo/models";
import { demoError, demoJson, v1 } from "@/mocks/http";

type Partial_ = Partial<ComponentConfig>;

const without = <T>(rec: Record<string, T>, key: string) =>
  Object.fromEntries(Object.entries(rec).filter(([k]) => k !== key));

const DeleteOverrideSchema = z.object({
  scope: z.enum(["project", "component", "item"]),
  scope_id: z.string().optional(),
  component_id: z.string(),
});

/** preset → project → component → item (SPEC 7.1), recording where each field came from. */
export function resolveConfig(componentId: string, item: string | null): ResolvedConfig | null {
  const db = getDb();
  const { preset: presetId, fallback_notify } = db.config.defaults;
  const preset = presetConfig(componentId, presetId, fallback_notify);
  if (!preset) return null;
  const layers: [ConfigSource, Partial_ | undefined][] = [
    ["project", db.config.project],
    ["component", db.config.component[componentId]],
    ["item", item ? db.config.item[`${componentId}|${item}`] : undefined],
  ];
  const values: ComponentConfig = preset;
  const sources = Object.fromEntries(CONFIG_FIELDS.map((f) => [f, "preset"])) as Record<
    (typeof CONFIG_FIELDS)[number],
    ConfigSource
  >;
  for (const [source, layer] of layers) {
    for (const field of CONFIG_FIELDS) {
      if (layer?.[field] === undefined) continue;
      (values as Record<string, unknown>)[field] = structuredClone(layer[field]);
      sources[field] = source;
    }
  }
  return { component_id: componentId, item, values, sources };
}

export const configHandlers = [
  http.get(v1("/config/components"), () =>
    demoJson({
      components: getDb().config.components,
      models: allModels,
      local_runtime_ok: true,
    }),
  ),

  // ?component=<id>&item=<type:id>
  http.get(v1("/config/resolve"), ({ request }) => {
    const q = new URL(request.url).searchParams;
    const component = q.get("component") ?? "";
    const resolved = resolveConfig(component, q.get("item"));
    return resolved ? demoJson(resolved) : demoError(404, "unknown_component", { id: component });
  }),

  http.put(v1("/config/override"), async ({ request }) => {
    const body = OverrideRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const { scope, scope_id, component_id, data } = body.data;
    const cfg = getDb().config;
    if (!resolveConfig(component_id, null))
      return demoError(404, "unknown_component", { id: component_id });
    if (scope === "project") cfg.project = { ...cfg.project, ...data };
    else if (scope === "component")
      cfg.component[component_id] = { ...cfg.component[component_id], ...data };
    else {
      if (!scope_id) return demoError(422, "invalid_request", { issues: "scope_id" });
      const key = `${component_id}|${scope_id}`;
      cfg.item[key] = { ...cfg.item[key], ...data };
    }
    return demoJson(resolveConfig(component_id, scope === "item" ? scope_id : null) ?? {});
  }),

  // 「恢复成预设」: ?scope=component&component_id=<id> (scope=item also takes scope_id).
  http.delete(v1("/config/override"), ({ request }) => {
    const q = DeleteOverrideSchema.safeParse(Object.fromEntries(new URL(request.url).searchParams));
    if (!q.success) return demoError(422, "invalid_request", { issues: q.error.message });
    const { scope, scope_id, component_id } = q.data;
    const cfg = getDb().config;
    if (!resolveConfig(component_id, null))
      return demoError(404, "unknown_component", { id: component_id });
    if (scope === "project") cfg.project = {};
    else if (scope === "component") cfg.component = without(cfg.component, component_id);
    else cfg.item = without(cfg.item, `${component_id}|${scope_id ?? ""}`);
    return demoJson(
      resolveConfig(component_id, scope === "item" ? (scope_id ?? null) : null) ?? {},
    );
  }),

  http.get(v1("/config/defaults"), () => demoJson(getDb().config.defaults)),

  http.put(v1("/config/defaults"), async ({ request }) => {
    const body = ConfigDefaultsSchema.partial().safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const cfg = getDb().config;
    cfg.defaults = { ...cfg.defaults, ...body.data };
    return demoJson(cfg.defaults);
  }),
];
