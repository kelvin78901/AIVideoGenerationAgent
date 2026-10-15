/**
 * Run settings per pipeline component (SPEC 7.1): three levels — project default → component
 * → single shot / asset — and, for every field, which level the value came from.
 */
import { z } from "zod";

import { MessageSchema } from "@/api/schemas/common";
import { ModelOptionSchema } from "@/api/schemas/models";

export const RunModeSchema = z.enum(["local", "api", "hybrid"]);
export type RunLocation = z.infer<typeof RunModeSchema>;

/** A component's mode: a run location, or `off` (skipped, e.g. no local version under 全本地). */
export const ConfigModeSchema = z.enum([...RunModeSchema.options, "off"]);
export type ConfigMode = z.infer<typeof ConfigModeSchema>;

export const FallbackTriggerSchema = z.enum(["error", "timeout", "qa_fail"]);
export type FallbackTrigger = z.infer<typeof FallbackTriggerSchema>;

export const FallbackSchema = z.object({
  enabled: z.boolean(),
  on: z.array(FallbackTriggerSchema),
  /** qa_fail fires after this many failed QA rounds in a row. */
  qa_fail_n: z.number().int().positive(),
  /** Local run timeout that counts as `timeout`. */
  timeout_s: z.number().int().positive(),
  /** Model to fall back to; null = next in `alt_order`. */
  to: z.string().nullable(),
  notify: z.enum(["after", "ask"]),
});
export type Fallback = z.infer<typeof FallbackSchema>;

export const ComponentConfigSchema = z.object({
  mode: ConfigModeSchema,
  api_model: z.string().nullable(),
  local_model: z.string().nullable(),
  fallback: FallbackSchema,
  /** 「不满意换一个」 order. */
  alt_order: z.array(z.string()),
  per_call_cap_usd: z.number().nullable(),
});
export type ComponentConfig = z.infer<typeof ComponentConfigSchema>;

export const CONFIG_FIELDS = [
  "mode",
  "api_model",
  "local_model",
  "fallback",
  "alt_order",
  "per_call_cap_usd",
] as const;
export type ConfigField = (typeof CONFIG_FIELDS)[number];

/** `preset` = the active preset / factory default; the others are `config_override` scopes. */
export const ConfigSourceSchema = z.enum(["preset", "project", "component", "item"]);
export type ConfigSource = z.infer<typeof ConfigSourceSchema>;

/** `GET /config/resolve?component=&item=` */
export const ResolvedConfigSchema = z.object({
  component_id: z.string(),
  /** `shot:1-05`, `asset:a3` … or null for the component level. */
  item: z.string().nullable(),
  values: ComponentConfigSchema,
  sources: z.record(z.enum(CONFIG_FIELDS), ConfigSourceSchema),
});
export type ResolvedConfig = z.infer<typeof ResolvedConfigSchema>;

/** `PUT /config/override` → the re-resolved config. */
export const OverrideRequestSchema = z.object({
  scope: z.enum(["project", "component", "item"]),
  /** Item id for scope=item (`shot:1-05`); null otherwise. */
  scope_id: z.string().nullable(),
  component_id: z.string(),
  data: ComponentConfigSchema.partial(),
});
export type OverrideRequest = z.infer<typeof OverrideRequestSchema>;

export const ComponentDefSchema = z.object({
  /** components.yaml id; the UI translates `enums:component.<id>`. */
  id: z.string(),
  stage: z.string(),
  kind: z.string(),
  /** In the order pickers list them (providers.yaml `llm_ui_order` for writing models). */
  api_models: z.array(z.string()),
  local_models: z.array(z.string()),
  /** Run locations that cannot be used, with the reason (no local model, machine too small …). */
  unavailable: z.partialRecord(RunModeSchema, MessageSchema),
});
export type ComponentDef = z.infer<typeof ComponentDefSchema>;

/** `GET /config/components` */
export const ComponentCatalogSchema = z.object({
  components: z.array(ComponentDefSchema),
  models: z.array(ModelOptionSchema),
  /** ComfyUI / the local LLM server answered the last health check. */
  local_runtime_ok: z.boolean(),
});
export type ComponentCatalog = z.infer<typeof ComponentCatalogSchema>;

/** The four one-click presets (SPEC 7.2; components.yaml `presets`). */
export const PresetIdSchema = z.enum(["quality", "balanced", "cheap", "local"]);
export type PresetId = z.infer<typeof PresetIdSchema>;

/** `GET / PUT /config/defaults`: the active preset and how fallbacks behave everywhere. */
export const ConfigDefaultsSchema = z.object({
  preset: PresetIdSchema,
  /** `after` = fall back and say so afterwards; `ask` = pause and ask first (SPEC 7.5). */
  fallback_notify: z.enum(["after", "ask"]),
});
export type ConfigDefaults = z.infer<typeof ConfigDefaultsSchema>;
