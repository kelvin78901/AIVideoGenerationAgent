/**
 * Component catalog and the balanced preset for the writing components (components.yaml).
 * Media components (img, kf, vid …) join with their pages' steps.
 * Defaults match the prototype's Inspector: 小说补全 API DeepSeek V4 Pro → Kimi K2.6, $0.5;
 * 设定提取 本地 Qwen3.6-27B → Qwen3.8-flash, $0.2.
 */
import type { ComponentConfig, ComponentDef } from "@/api/schemas/config";
import { llmApiModels, llmLocalModels } from "@/mocks/fixtures/demo/models";

const LLM_API = llmApiModels.map((m) => m.key);
const LLM_LOCAL = llmLocalModels.map((m) => m.key);
const LOCAL = "local/qwen3.6-27b";

function llm(id: string, stage: string, local = LLM_LOCAL): ComponentDef {
  return { id, stage, kind: "llm", api_models: LLM_API, local_models: local, unavailable: {} };
}

export const componentDefs: ComponentDef[] = [
  llm("extract", "novel"),
  llm("enrich", "novel"),
  llm("split", "script"),
  llm("script", "script"),
  llm("assets", "assets"),
  llm("plan", "storyboard", [LOCAL]),
];

/** 「不满意换一个」: the fallback target first, then the other models (local first). */
function altOrder(primary: string, to: string): string[] {
  const rest = [...LLM_LOCAL, ...LLM_API].filter((k) => k !== primary && k !== to);
  return [to, ...rest];
}

function balanced(
  mode: ComponentConfig["mode"],
  api: string,
  to: string,
  cap: number,
): ComponentConfig {
  const primary = mode === "api" ? api : LOCAL;
  return {
    mode,
    api_model: api,
    local_model: LOCAL,
    fallback: {
      enabled: true,
      on: ["error", "timeout"],
      qa_fail_n: 2,
      timeout_s: 600,
      to,
      notify: "after",
    },
    alt_order: altOrder(primary, to),
    per_call_cap_usd: cap,
  };
}

export const presetConfigs: Record<string, ComponentConfig> = {
  extract: balanced("local", "qwen/qwen3.8-flash", "qwen/qwen3.8-flash", 0.2),
  enrich: balanced("api", "deepseek/v4-pro", "moonshot/kimi-k2.6", 0.5),
  split: balanced("api", "deepseek/v4.1-flash", "qwen/qwen3.7-plus", 0.3),
  script: balanced("api", "deepseek/v4-pro", "qwen/qwen3.8-max", 0.5),
  assets: balanced("api", "deepseek/v4.1-flash", "qwen/qwen3.7-plus", 0.3),
  plan: balanced("api", "deepseek/v4-pro", "moonshot/kimi-k2.6", 0.5),
};

/** The model a plain run uses: local for local / hybrid drafts, the API model otherwise. */
export function primaryModel(cfg: ComponentConfig): string | null {
  return cfg.mode === "api" ? cfg.api_model : (cfg.local_model ?? cfg.api_model);
}
