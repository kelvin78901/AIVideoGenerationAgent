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

export function modelByKey(key: string): ModelOption | undefined {
  return llmModels.find((m) => m.key === key);
}
