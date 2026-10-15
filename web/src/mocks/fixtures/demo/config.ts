/**
 * Component catalog and the balanced preset for the writing components (components.yaml).
 * Media components (img, kf, vid …) join with their pages' steps.
 * Defaults match the prototype's Inspector: 小说补全 API DeepSeek V4 Pro → Kimi K2.6, $0.5;
 * 设定提取 本地 Qwen3.6-27B → Qwen3.8-flash, $0.2.
 */
import type { ComponentConfig, ComponentDef, Fallback, PresetId } from "@/api/schemas/config";
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

/** In components.yaml order (the Models page lists them this way). */
export const componentDefs: ComponentDef[] = [
  llm("extract", "novel"),
  llm("enrich", "novel"),
  llm("split", "script"),
  llm("script", "script"),
  llm("assets", "assets"),
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
  llm("plan", "storyboard", [LOCAL]),
  media("kf", "storyboard", "image", IMG_API, ["comfy/qwen-image-edit", "comfy/flux2-dev"]),
  media("world", "storyboard", "world", ["worldlabs/marble"], []),
  // Generate step (prototype Generate.dc.html Inspector).
  media(
    "vid",
    "generate",
    "video",
    ["minimax/h3-api", "volc/seedance-2.5", "kling/kling-3.0", "google/veo-3.1"],
    ["comfy/h3", "comfy/wan-2.2", "comfy/ltx"],
  ),
  media("ctrl", "generate", "video", [], ["comfy/h3-fun-controlnet"]),
  media(
    "up",
    "generate",
    "upscale",
    ["minimax/h3-regenerate-2k", "topaz/starlight-precise-2.5"],
    ["comfy/seedvr2", "comfy/flashvsr"],
  ),
  media("lip", "generate", "lipsync", ["sync/lipsync-2-pro"], ["local/latentsync"]),
  media(
    "qa",
    "generate",
    "vlm",
    ["google/gemini-3.6-flash", "google/gemini-3.1-flash-lite"],
    ["local/qwen3-vl-32b"],
  ),
  // Post step (prototype Post.dc.html Inspector).
  media("music", "post", "music", ["elevenlabs/music"], ["local/ace-step"]),
  media("sfx", "post", "sfx", ["elevenlabs/sfx"], ["local/mmaudio"]),
  media(
    "sub",
    "post",
    "asr",
    ["elevenlabs/scribe"],
    ["local/whisper-large-v3", "local/paraformer"],
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
  plan: balanced("api", "deepseek/v4-pro", "moonshot/kimi-k2.6", 0.8),
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
  kf: route(
    "kf",
    "hybrid",
    "google/nano-banana-pro",
    "comfy/qwen-image-edit",
    "volc/seedream-5.0",
    1,
  ),
  voice: route("voice", "api", "minimax/speech-2.8-hd", "local/indextts2", "local/indextts2", 3),
  // Prototype Generate.dc.html: 视频 混合 (本地 H3 草稿, H3 API 终版), $2; 精修 本地 SeedVR2, $1;
  // 口型 API sync, $0.5; 质检 本地 Qwen3-VL, $0.2.
  vid: route("vid", "hybrid", "minimax/h3-api", "comfy/h3", "minimax/h3-api", 2),
  up: route(
    "up",
    "local",
    "minimax/h3-regenerate-2k",
    "comfy/seedvr2",
    "minimax/h3-regenerate-2k",
    1,
  ),
  lip: route("lip", "api", "sync/lipsync-2-pro", "local/latentsync", "local/latentsync", 0.5),
  qa: route(
    "qa",
    "local",
    "google/gemini-3.6-flash",
    "local/qwen3-vl-32b",
    "google/gemini-3.6-flash",
    0.2,
  ),
  // Prototype Post.dc.html: 配乐 API ElevenLabs Music, $0.5; 音效 本地 MMAudio, $0.3;
  // 字幕对齐 本地 Whisper, $0.1.
  music: route("music", "api", "elevenlabs/music", "local/ace-step", "local/ace-step", 0.5),
  sfx: route("sfx", "local", "elevenlabs/sfx", "local/mmaudio", "elevenlabs/sfx", 0.3),
  sub: route(
    "sub",
    "local",
    "elevenlabs/scribe",
    "local/whisper-large-v3",
    "elevenlabs/scribe",
    0.1,
  ),
  // components.yaml: 3D 场景 balanced `mode: off` (v1 placeholder); 结构控制 local only.
  world: single("off", "worldlabs/marble", null),
  ctrl: single("local", null, "comfy/h3-fun-controlnet"),
};

/** A component with a single model: nothing to fall back to or switch between. */
function single(
  mode: ComponentConfig["mode"],
  api: string | null,
  local: string | null,
): ComponentConfig {
  return {
    mode,
    api_model: api,
    local_model: local,
    fallback: {
      enabled: false,
      on: ["error", "timeout"],
      qa_fail_n: 2,
      timeout_s: 600,
      to: null,
      notify: "after",
    },
    alt_order: [],
    per_call_cap_usd: api ? 1 : null,
  };
}

/** 省钱 picks this API model (components.yaml `cheap_api`; prototype `cheap`); else the last one. */
const CHEAP_API: Record<string, string> = {
  extract: "qwen/qwen3.8-flash",
  enrich: "deepseek/v4.1-flash",
  split: "deepseek/v4.1-flash",
  script: "deepseek/v4.1-flash",
  assets: "deepseek/v4.1-flash",
  plan: "deepseek/v4.1-flash",
  img: "volc/seedream-5.0",
  kf: "volc/seedream-5.0",
  text: "google/nano-banana-pro",
  voice: "minimax/speech-2.8-hd",
  up: "minimax/h3-regenerate-2k",
  qa: "google/gemini-3.1-flash-lite",
};

/**
 * One component's preset layer (SPEC 7.2, prototype `presetCfg()`): 质量优先 = best API, local
 * only as fallback; 均衡 = the tuned table above; 省钱 = local first, the cheapest API as
 * fallback; 全本地 = local only, components without a local version are skipped.
 */
export function presetConfig(
  id: string,
  preset: PresetId,
  notify: Fallback["notify"],
): ComponentConfig | null {
  const def = componentDefs.find((d) => d.id === id);
  const bal = presetConfigs[id];
  if (!def || !bal) return null;
  const apis = def.api_models;
  const locals = def.local_models;
  const both = apis.length > 0 && locals.length > 0;
  let cfg: ComponentConfig;
  if (preset === "quality" || preset === "cheap") {
    const api = (preset === "quality" ? apis[0] : (CHEAP_API[id] ?? apis.at(-1))) ?? null;
    const local = locals[0] ?? null;
    const mode =
      preset === "quality" ? (apis.length ? "api" : "local") : locals.length ? "local" : "api";
    const to = both ? (mode === "api" ? local : api) : null;
    cfg = {
      ...bal,
      mode,
      api_model: api,
      local_model: local,
      fallback: { ...bal.fallback, enabled: both, to },
      alt_order: altAfter(def, mode === "api" ? api : local, to),
    };
  } else if (preset === "local") {
    const local = locals[0] ?? null;
    cfg = {
      ...bal,
      mode: local ? "local" : "off",
      local_model: local,
      fallback: { ...bal.fallback, enabled: false, to: null },
      alt_order: locals.filter((k) => k !== local),
    };
  } else cfg = structuredClone(bal);
  return { ...cfg, fallback: { ...cfg.fallback, notify } };
}

/** 「不满意换一个」 after a preset change: the fallback target, then the rest (local first). */
function altAfter(def: ComponentDef, primary: string | null, to: string | null): string[] {
  const rest = [...def.local_models, ...def.api_models].filter((k) => k !== primary && k !== to);
  return to ? [to, ...rest] : rest;
}

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
  if (cfg.mode === "off") return null;
  return cfg.mode === "api" ? cfg.api_model : (cfg.local_model ?? cfg.api_model);
}
