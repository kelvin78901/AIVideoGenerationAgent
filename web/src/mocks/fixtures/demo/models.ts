/**
 * Writing models (providers.yaml `llm_providers`, in `llm_ui_order`) and the local LLMs, as the
 * demo pickers list them. Step 5's `/config/components` builds the per-component lists from here.
 */
import type { ModelOption } from "@/api/schemas/models";

const mtok = (input: number, output: number, currency: "USD" | "CNY" = "USD") =>
  ({ unit: "mtok", in: input, out: output, currency }) as const;

export const llmApiModels: ModelOption[] = [
  { key: "deepseek/v4-pro", display: "DeepSeek V4 Pro", where: "api", price: mtok(1.32, 3.96) },
  {
    key: "deepseek/v4.1-flash",
    display: "DeepSeek V4.1 Flash",
    where: "api",
    price: mtok(0.3, 1.2),
  },
  { key: "moonshot/kimi-k2.6", display: "Kimi K2.6", where: "api", price: mtok(0.95, 4) },
  { key: "qwen/qwen3.8-max", display: "Qwen3.8-max", where: "api", price: mtok(2, 6) },
  { key: "qwen/qwen3.7-plus", display: "Qwen3.7-plus", where: "api", price: mtok(0.4, 1.6) },
  { key: "volc/doubao-2.1-pro", display: "豆包 2.1 Pro", where: "api", price: mtok(6, 30, "CNY") },
  { key: "zhipu/glm-5.3", display: "GLM-5.3", where: "api", price: mtok(1.4, 4.4) },
  { key: "minimax/m3", display: "MiniMax-M3", where: "api", price: mtok(0.3, 1.2) },
  { key: "qwen/qwen3.8-flash", display: "Qwen3.8-flash", where: "api", price: mtok(0.15, 0.47) },
  { key: "zhipu/glm-5.3-flash", display: "GLM-5.3-Flash", where: "api", price: mtok(0.15, 0.5) },
  {
    key: "google/gemini-3.6-flash",
    display: "Gemini 3.6 Flash",
    where: "api",
    price: mtok(0.75, 3.75),
  },
  { key: "openai/gpt-6-luna", display: "GPT-6 Luna", where: "api", price: mtok(0.1, 0.5) },
  {
    key: "openrouter/claude-sonnet-5.5",
    display: "Claude Sonnet 5.5 · OpenRouter",
    where: "api",
    price: null,
  },
  { key: "openrouter/any", display: "OpenRouter", where: "api", price: null },
  { key: "custom", display: "OpenAI-compatible", where: "api", price: null },
];

export const llmLocalModels: ModelOption[] = [
  { key: "local/qwen3.6-27b", display: "Qwen3.6-27B", where: "local", price: null },
  { key: "local/qwen3-30b-a3b", display: "Qwen3-30B-A3B", where: "local", price: null },
];

export const llmModels: ModelOption[] = [...llmLocalModels, ...llmApiModels];

const per = (unit: "image" | "mchar", amount: number) =>
  ({ unit, amount, currency: "USD" }) as const;

/** Image and voice models (providers.yaml `media_models`, `local_models`). */
export const mediaModels: ModelOption[] = [
  { key: "openai/gpt-image-2", display: "GPT Image 2", where: "api", price: per("image", 0.28) },
  {
    key: "google/nano-banana-pro",
    display: "Nano Banana Pro",
    where: "api",
    price: per("image", 0.14),
  },
  { key: "volc/seedream-5.0", display: "Seedream 5.0", where: "api", price: per("image", 0.03) },
  { key: "comfy/qwen-image-edit", display: "Qwen-Image-Edit", where: "local", price: null },
  { key: "comfy/qwen-image", display: "Qwen-Image", where: "local", price: null },
  { key: "comfy/flux2-dev", display: "FLUX.2 dev", where: "local", price: null },
  {
    key: "minimax/speech-2.8-hd",
    display: "MiniMax Speech 2.8 HD",
    where: "api",
    price: per("mchar", 100),
  },
  { key: "elevenlabs/v3", display: "ElevenLabs v3", where: "api", price: null },
  { key: "local/indextts2", display: "IndexTTS2", where: "local", price: null },
  { key: "local/cosyvoice", display: "CosyVoice", where: "local", price: null },
  { key: "local/qwen3-tts", display: "Qwen3-TTS", where: "local", price: null },
];

const perSecond = (amount: number) => ({ unit: "second", amount, currency: "USD" }) as const;

/**
 * Generate step (prototype Generate.dc.html): video, 2K finishing, lip-sync and QA models.
 * Per-minute list prices are shown per second (Seedance 2.5: $24.60 / min ≈ $0.41 / s);
 * H3 Regenerate-2K is $0.05 / s out + $0.05 / s in.
 */
export const generateModels: ModelOption[] = [
  { key: "comfy/h3", display: "MiniMax H3（本地）", where: "local", price: null },
  { key: "comfy/wan-2.2", display: "Wan 2.2（本地）", where: "local", price: null },
  { key: "comfy/ltx", display: "LTX-2.3（本地）", where: "local", price: null },
  { key: "minimax/h3-api", display: "MiniMax H3 API", where: "api", price: perSecond(0.08) },
  { key: "volc/seedance-2.5", display: "Seedance 2.5", where: "api", price: perSecond(0.41) },
  { key: "kling/kling-3.0", display: "Kling 3.0", where: "api", price: null },
  { key: "google/veo-3.1", display: "Veo 3.1", where: "api", price: null },
  { key: "comfy/seedvr2", display: "SeedVR2（本地）", where: "local", price: null },
  { key: "comfy/flashvsr", display: "FlashVSR（本地）", where: "local", price: null },
  {
    key: "minimax/h3-regenerate-2k",
    display: "H3 Regenerate-2K",
    where: "api",
    price: perSecond(0.1),
  },
  {
    key: "topaz/starlight-precise-2.5",
    display: "Topaz Starlight",
    where: "api",
    price: perSecond(0.12),
  },
  { key: "local/latentsync", display: "LatentSync（本地）", where: "local", price: null },
  {
    key: "sync/lipsync-2-pro",
    display: "sync lipsync-2-pro",
    where: "api",
    price: perSecond(0.075),
  },
  { key: "local/qwen3-vl-32b", display: "Qwen3-VL-32B（本地）", where: "local", price: null },
  // Post (prototype Post.dc.html).
  { key: "elevenlabs/music", display: "ElevenLabs Music", where: "api", price: null },
  { key: "local/ace-step", display: "ACE-Step（本地）", where: "local", price: null },
  { key: "local/mmaudio", display: "MMAudio（本地）", where: "local", price: null },
  { key: "elevenlabs/sfx", display: "ElevenLabs 音效", where: "api", price: null },
  {
    key: "local/whisper-large-v3",
    display: "Whisper large-v3（本地）",
    where: "local",
    price: null,
  },
  { key: "local/paraformer", display: "Paraformer（本地）", where: "local", price: null },
  { key: "elevenlabs/scribe", display: "ElevenLabs Scribe", where: "api", price: null },
  // Models page only: 3D 场景 (API only, v1 placeholder) and 结构控制 (local only).
  { key: "worldlabs/marble", display: "World Labs Marble", where: "api", price: null },
  {
    key: "comfy/h3-fun-controlnet",
    display: "H3 Fun ControlNet（本地）",
    where: "local",
    price: null,
  },
  {
    key: "google/gemini-3.1-flash-lite",
    display: "Gemini 3.1 Flash-Lite",
    where: "api",
    price: mtok(0.25, 1.5),
  },
];

export const allModels: ModelOption[] = [...llmModels, ...mediaModels, ...generateModels];

export function modelByKey(key: string): ModelOption | undefined {
  return allModels.find((m) => m.key === key);
}
