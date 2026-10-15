/**
 * First-run scan of the two sample machines in the prototype (Setup.dc.html `items()`):
 * Kelvin's PC (Windows + RTX 5090) and a Mac M4 Pro. The demo starts before the first scan.
 */
import type { Machine, MachineProfile, SetupGroup, SetupItem } from "@/api/schemas/setup";

export type DemoMachine = "pc" | "mac";

export const machines: Record<DemoMachine, Machine> = {
  pc: { os: "windows", gpu: { name: "RTX 5090", vram_gb: 32, backend: "cuda" } },
  mac: { os: "macos", gpu: { name: "Apple M4 Pro", vram_gb: 48, backend: "mps" } },
};

type Msg = [code: string, params?: Record<string, string | number>];

/** Scan answer of one item; `dl` items are large downloads (they install slower in the demo). */
export interface DemoItem extends Omit<SetupItem, "found" | "fix" | "install"> {
  found: SetupItem["found"];
  fix: SetupItem["fix"];
  dl: boolean;
}

const msg = (m: Msg | null) => (m ? { code: m[0], params: m[1] ?? {} } : null);

function I(
  id: string,
  group: SetupGroup,
  name: string | [zh: string, en: string],
  found: Msg,
  status: DemoItem["status"],
  fix: Msg | null,
  opts: { required?: boolean; installable?: boolean; dl?: boolean } = {},
): DemoItem {
  const [zh, en] = typeof name === "string" ? [name, name] : name;
  return {
    id,
    group,
    name: { zh, en },
    status,
    found: msg(found),
    fix: msg(fix),
    required: opts.required ?? false,
    installable: opts.installable ?? false,
    dl: opts.dl ?? false,
  };
}

const req = { required: true, installable: true };
const opt = { installable: true };

export const scanResults: Record<DemoMachine, DemoItem[]> = {
  pc: [
    I(
      "os",
      "sys",
      ["操作系统", "Operating system"],
      ["os", { name: "Windows 11", bits: 64 }],
      "ok",
      null,
    ),
    I("gpu", "sys", ["显卡", "GPU"], ["gpu_vram", { name: "NVIDIA RTX 5090", gb: 32 }], "ok", null),
    I("driver", "sys", ["显卡驱动", "GPU driver"], ["driver_cuda", { cuda: 13 }], "ok", null),
    I("ram", "sys", ["内存", "Memory"], ["ram", { gb: 64 }], "ok", null),
    I(
      "disk",
      "sys",
      ["磁盘空间", "Disk space"],
      ["disk_free_on", { drive: "D:", free: "1.2 TB" }],
      "ok",
      null,
    ),
    I("python", "rt", "Python", ["version", { version: "3.12" }], "ok", null),
    I(
      "torch",
      "rt",
      "PyTorch",
      ["torch_not_cuda", { cuda: 13 }],
      "old",
      ["torch_cuda", { cuda: "13.0" }],
      req,
    ),
    I(
      "ffmpeg",
      "rt",
      "FFmpeg",
      ["not_found"],
      "missing",
      ["install_named", { name: "FFmpeg" }],
      req,
    ),
    I("git", "rt", "Git", ["installed"], "ok", null),
    I("comfy", "comfy", "ComfyUI", ["outdated"], "old", ["update_latest"], req),
    I(
      "node_h3",
      "comfy",
      ["MiniMax H3 节点", "MiniMax H3 nodes"],
      ["not_found"],
      "missing",
      ["install_nodes"],
      req,
    ),
    I("node_vhs", "comfy", "VideoHelperSuite", ["installed"], "ok", null),
    I(
      "node_seedvr2",
      "comfy",
      ["SeedVR2 节点（本地超分）", "SeedVR2 nodes (local upscaling)"],
      ["not_found"],
      "missing",
      ["install_nodes"],
      req,
    ),
    I(
      "node_flashvsr",
      "comfy",
      ["FlashVSR 节点（快速超分）", "FlashVSR nodes (fast upscaling)"],
      ["not_found"],
      "optional",
      ["install_nodes"],
      opt,
    ),
    I(
      "node_ctrl",
      "comfy",
      ["Fun ControlNet 节点", "Fun ControlNet nodes"],
      ["not_found"],
      "optional",
      ["ctrl_later"],
      opt,
    ),
    I(
      "sage",
      "comfy",
      ["SageAttention 加速", "SageAttention speed-up"],
      ["not_found"],
      "optional",
      ["sage_build"],
      opt,
    ),
    I(
      "w_h3",
      "w",
      ["MiniMax H3 权重（int8）", "MiniMax H3 weights (int8)"],
      ["not_found"],
      "missing",
      ["download"],
      { ...req, dl: true },
    ),
    I(
      "w_te",
      "w",
      ["Qwen3-VL-32B 文本编码器（NVFP4）", "Qwen3-VL-32B text encoder (NVFP4)"],
      ["not_found"],
      "missing",
      ["download"],
      { ...req, dl: true },
    ),
    I("w_img", "w", "Qwen-Image-Edit", ["not_found"], "missing", ["download"], {
      ...req,
      dl: true,
    }),
    I("w_sr", "w", ["SeedVR2 权重", "SeedVR2 weights"], ["not_found"], "missing", ["download"], {
      ...req,
      dl: true,
    }),
    I("w_tts", "w", "IndexTTS2", ["not_found"], "missing", ["download"], { ...req, dl: true }),
    I(
      "w_llm",
      "w",
      ["Qwen3.6-27B（本地 LLM）", "Qwen3.6-27B (local LLM)"],
      ["not_found"],
      "optional",
      ["llm_optional"],
      { ...opt, dl: true },
    ),
    I("hf", "svc", ["模型下载网络", "Model download network"], ["hf_slow"], "warn", [
      "pick_mirror",
    ]),
    I(
      "llmsrv",
      "svc",
      ["本地 LLM 服务", "Local LLM server"],
      ["not_found"],
      "optional",
      ["install_llm_server"],
      opt,
    ),
    I("keys", "svc", ["API 密钥", "API keys"], ["no_keys"], "optional", ["keys_later"]),
  ],
  mac: [
    I("os", "sys", ["操作系统", "Operating system"], ["os_apple", { name: "macOS" }], "ok", null),
    I("gpu", "sys", ["显卡", "GPU"], ["gpu_unified", { name: "Apple M4 Pro" }], "warn", [
      "no_cuda_video_api",
    ]),
    I("ram", "sys", ["内存", "Memory"], ["ram_unified", { gb: 48 }], "ok", null),
    I("disk", "sys", ["磁盘空间", "Disk space"], ["disk_free", { free: "600 GB" }], "ok", null),
    I("python", "rt", "Python", ["version", { version: "3.12" }], "ok", null),
    I("torch", "rt", "PyTorch", ["not_found"], "missing", ["install_torch_mps"], req),
    I(
      "ffmpeg",
      "rt",
      "FFmpeg",
      ["not_found"],
      "missing",
      ["install_named", { name: "FFmpeg" }],
      req,
    ),
    I("git", "rt", "Git", ["installed"], "ok", null),
    I("comfy", "comfy", "ComfyUI", ["not_found"], "optional", ["comfy_images_only"], opt),
    I("node_h3", "comfy", ["MiniMax H3 节点", "MiniMax H3 nodes"], ["needs_cuda"], "skip", [
      "unsupported_skip",
    ]),
    I(
      "node_sr",
      "comfy",
      ["SeedVR2 / FlashVSR 节点", "SeedVR2 / FlashVSR nodes"],
      ["needs_cuda"],
      "skip",
      ["unsupported_upscale_api"],
    ),
    I(
      "w_llm",
      "w",
      ["Qwen3.6-27B（MLX 版）", "Qwen3.6-27B (MLX)"],
      ["not_found"],
      "missing",
      ["download_local_writing"],
      { ...req, dl: true },
    ),
    I(
      "w_tts",
      "w",
      ["本地配音模型", "Local voice model"],
      ["not_found"],
      "optional",
      ["mac_voice_slow"],
      { ...opt, dl: true },
    ),
    I("w_img", "w", "Qwen-Image-Edit", ["not_found"], "optional", ["mac_image_slow"], {
      ...opt,
      dl: true,
    }),
    I("hf", "svc", ["模型下载网络", "Model download network"], ["hf_slow"], "warn", [
      "pick_mirror",
    ]),
    I(
      "llmsrv",
      "svc",
      ["本地 LLM 服务", "Local LLM server"],
      ["not_found"],
      "missing",
      ["install_ollama_mlx"],
      req,
    ),
    I("keys", "svc", ["API 密钥", "API keys"], ["no_keys"], "warn", ["keys_video_api"]),
  ],
};

/** The item that always fails in the demo (prototype: SageAttention stops at 60 %). */
export const FAILING_ITEM = "sage";

export const recommendations: Record<DemoMachine, NonNullable<MachineProfile["recommendation"]>> = {
  pc: { preset: "balanced", reason: "local_video" },
  mac: { preset: "balanced", reason: "no_cuda" },
};

export const DEFAULT_DIR: Record<DemoMachine, string> = {
  pc: "D:\\DramaStudio",
  mac: "~/DramaStudio",
};

/** Before the first scan: the quick hardware probe is known (top bar GPU), nothing else. */
export function idleProfile(machine: DemoMachine): MachineProfile {
  return {
    scanned_at: null,
    machine: machines[machine],
    phase: "idle",
    items: [],
    install: null,
    default_dir: DEFAULT_DIR[machine],
    recommendation: null,
  };
}

export const profile: MachineProfile = idleProfile("pc");
