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

const IMG_API = ["openai/gpt-image-2", "google/nano-banana-pro", "volc/seedream-5.0"];

function media(id: string, stage: string, kind: string, api: string[], local: string[]) {
  return { id, stage, kind, api_models: api, local_models: local, unavailable: {} };
}

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
  media("img", "assets", "image", IMG_API, ["comfy/qwen-image-edit", "comfy/flux2-dev"]),
  media(
    "text",
    "assets",
    "image",
    ["openai/gpt-image-2", "google/nano-banana-pro"],
    ["comfy/qwen-image"],
  ),
  media(
    "voice",
    "assets",
    "tts",
    ["minimax/speech-2.8-hd", "elevenlabs/v3"],
    ["local/indextts2", "local/cosyvoice", "local/qwen3-tts"],
  ),
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
  script: balanced("api", "deepseek/v4-pro", "qwen/qwen3.8-max", 0.8),
  assets: balanced("api", "deepseek/v4.1-flash", "qwen/qwen3.7-plus", 0.3),
  plan: balanced("api", "deepseek/v4-pro", "moonshot/kimi-k2.6", 0.5),
  // Prototype Assets.dc.html: 参考图 混合 (本地草稿 Qwen-Image-Edit, 终版 Nano Banana Pro).
  img: route(
    "img",
    "hybrid",
    "google/nano-banana-pro",
    "comfy/qwen-image-edit",
    "volc/seedream-5.0",
    1.5,
  ),
  text: route(
    "text",
    "api",
    "openai/gpt-image-2",
    "comfy/qwen-image",
    "google/nano-banana-pro",
    1.2,
  ),
  voice: route("voice", "api", "minimax/speech-2.8-hd", "local/indextts2", "local/indextts2", 3),
};

/** A media component's route; 「不满意换一个」 order = fallback target, then its other models. */
function route(
  id: string,
  mode: ComponentConfig["mode"],
  api: string,
  local: string,
  to: string,
  cap: number,
): ComponentConfig {
  const def = componentDefs.find((d) => d.id === id);
  const keys = [...(def?.local_models ?? []), ...(def?.api_models ?? [])];
  const primary = mode === "api" ? api : local;
  return {
    ...balanced(mode, api, to, cap),
    local_model: local,
    alt_order: [to, ...keys.filter((k) => k !== to && k !== primary)],
  };
}

/** The model a plain run uses: local for local / hybrid drafts, the API model otherwise. */
export function primaryModel(cfg: ComponentConfig): string | null {
  return cfg.mode === "api" ? cfg.api_model : (cfg.local_model ?? cfg.api_model);
}
