/**
 * Workflow library demo (SPEC 6.4): the studio's recommended H3 and SeedVR2 workflows, one of
 * Kelvin's own that passed its trial, a community workflow whose guessed bindings wait for a yes,
 * and one that needs two node packs and a model first. Times are Beijing time, like the demo.
 */
import type {
  Binding,
  ComfyWorkflowFile,
  Workflow,
  WorkflowNode,
  WorkflowTrial,
} from "@/api/schemas/workflows";

const DRAFT = { w: 768, h: 1366, seconds: 3 };

const ds = (
  slot: Binding["slot"],
  node_title: string,
  node_class: string,
  field: string | null,
): Binding => ({ slot, index: null, node_title, node_class, field, state: "dramastudio" });

const bind = (
  slot: Binding["slot"],
  node_title: string,
  node_class: string,
  field: string | null,
  state: Binding["state"] = "confirmed",
  index: number | null = null,
): Binding => ({ slot, index, node_title, node_class, field, state });

const node = (title: string, class_type: string, fields: string[] = []): WorkflowNode => ({
  title,
  class_type,
  fields,
});

const passed = (at: string, duration_s: number, vram_gb: number): WorkflowTrial => ({
  at,
  status: "passed",
  job_id: null,
  ...DRAFT,
  duration_s,
  vram_gb,
  error: null,
});

const ok = (at: string, total: number) => ({
  at,
  status: "ok" as const,
  node_classes: { found: total, total },
  missing_packs: [],
  missing_models: [],
  problems: [],
});

const H3_NODES = [
  node("DramaStudio · 首帧", "DramaStudioImageInput", ["image"]),
  node("DramaStudio · 提示词", "DramaStudioPromptInput", ["positive", "negative"]),
  node("DramaStudio · 台词音频", "DramaStudioAudioInput", ["audio"]),
  node("DramaStudio · 尺寸与时长", "DramaStudioSpecInput", ["width", "height", "fps", "seconds"]),
  node("DramaStudio · 种子", "DramaStudioSeedInput", ["seed"]),
  node("H3 · 图生视频", "MiniMaxH3ImageToVideo", ["steps", "cfg"]),
  node("DramaStudio · 视频输出", "DramaStudioVideoOutput"),
];

const WAN_NODES = [
  node("Load Image", "LoadImage", ["image"]),
  node("Positive Prompt", "CLIPTextEncode", ["text"]),
  node("Negative Prompt", "CLIPTextEncode", ["text"]),
  node("WanImageToVideo", "WanImageToVideo", ["width", "height", "length", "batch_size"]),
  node("KSampler (high noise)", "KSamplerAdvanced", ["noise_seed", "steps", "cfg"]),
  node("KSampler (low noise)", "KSamplerAdvanced", ["noise_seed", "steps", "cfg"]),
  node("Create Video", "CreateVideo", ["fps"]),
  node("Save Video", "SaveVideo", ["filename_prefix"]),
];

export const workflows: Workflow[] = [
  {
    id: "wf_h3",
    slug: "h3-draft",
    model_key: "comfy/h3-draft",
    name: "MiniMax H3 · 视频草稿",
    tier: "recommended",
    source: "repo",
    origin: null,
    components: ["vid"],
    caps: {
      aspects: ["9:16", "16:9", "3:4", "1:1", "21:9"],
      max_seconds: 10,
      refs: 1,
      vram_gb: 24,
    },
    file_sha256: "4be1c07d9a3f2e8b6c5d1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d",
    file_changed: false,
    uses_dramastudio_nodes: true,
    bindings: [
      ds("first_frame", "DramaStudio · 首帧", "DramaStudioImageInput", "image"),
      ds("prompt", "DramaStudio · 提示词", "DramaStudioPromptInput", "positive"),
      ds("negative", "DramaStudio · 提示词", "DramaStudioPromptInput", "negative"),
      ds("dialogue_audio", "DramaStudio · 台词音频", "DramaStudioAudioInput", "audio"),
      ds("width", "DramaStudio · 尺寸与时长", "DramaStudioSpecInput", "width"),
      ds("height", "DramaStudio · 尺寸与时长", "DramaStudioSpecInput", "height"),
      ds("fps", "DramaStudio · 尺寸与时长", "DramaStudioSpecInput", "fps"),
      ds("seconds", "DramaStudio · 尺寸与时长", "DramaStudioSpecInput", "seconds"),
      ds("seed", "DramaStudio · 种子", "DramaStudioSeedInput", "seed"),
      ds("video_out", "DramaStudio · 视频输出", "DramaStudioVideoOutput", null),
    ],
    nodes: H3_NODES,
    check: ok("2026-10-18T09:12:00+08:00", 14),
    trial: passed("2026-10-17T21:40:00+08:00", 52, 22.4),
    created_at: "2026-10-15T10:00:00+08:00",
    updated_at: "2026-10-18T09:12:00+08:00",
  },
  {
    id: "wf_seedvr2",
    slug: "seedvr2-2k",
    model_key: "comfy/seedvr2-2k",
    name: "SeedVR2 · 2K 超分",
    tier: "recommended",
    source: "repo",
    origin: null,
    components: ["up"],
    caps: {
      aspects: ["9:16", "16:9", "3:4", "1:1", "21:9"],
      max_seconds: null,
      refs: null,
      vram_gb: 18,
    },
    file_sha256: "9c2e7f1a0b3d5c8e6f4a2b1d0c9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e",
    file_changed: false,
    uses_dramastudio_nodes: true,
    bindings: [
      ds("video_in", "DramaStudio · 输入视频", "DramaStudioVideoInput", "video"),
      ds("width", "DramaStudio · 尺寸与时长", "DramaStudioSpecInput", "width"),
      ds("height", "DramaStudio · 尺寸与时长", "DramaStudioSpecInput", "height"),
      ds("video_out", "DramaStudio · 视频输出", "DramaStudioVideoOutput", null),
    ],
    nodes: [
      node("DramaStudio · 输入视频", "DramaStudioVideoInput", ["video"]),
      node("DramaStudio · 尺寸与时长", "DramaStudioSpecInput", [
        "width",
        "height",
        "fps",
        "seconds",
      ]),
      node("SeedVR2 · 超分", "SeedVR2VideoUpscaler", ["model", "batch_size"]),
      node("DramaStudio · 视频输出", "DramaStudioVideoOutput"),
    ],
    check: ok("2026-10-18T09:12:00+08:00", 6),
    trial: passed("2026-10-17T21:52:00+08:00", 31, 17.6),
    created_at: "2026-10-15T10:00:00+08:00",
    updated_at: "2026-10-18T09:12:00+08:00",
  },
  {
    id: "wf_latentsync",
    slug: "latentsync-lip",
    model_key: "comfy/latentsync-lip",
    name: "LatentSync 口型",
    tier: "mine",
    source: "user",
    origin: "我的/口型-latentsync.json",
    components: ["lip"],
    caps: { aspects: ["9:16", "16:9", "3:4", "1:1"], max_seconds: 20, refs: null, vram_gb: 10 },
    file_sha256: "1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e",
    file_changed: false,
    uses_dramastudio_nodes: false,
    bindings: [
      bind("video_in", "Load Video", "VHS_LoadVideo", "video"),
      bind("dialogue_audio", "Load Audio", "LoadAudio", "audio"),
      bind("seed", "LatentSync", "LatentSyncNode", "seed"),
      bind("fps", "Video Combine", "VHS_VideoCombine", "frame_rate"),
      bind("video_out", "Video Combine", "VHS_VideoCombine", null),
    ],
    nodes: [
      node("Load Video", "VHS_LoadVideo", ["video", "force_rate"]),
      node("Load Audio", "LoadAudio", ["audio"]),
      node("LatentSync", "LatentSyncNode", ["seed", "lips_expression"]),
      node("Video Combine", "VHS_VideoCombine", ["frame_rate", "format"]),
    ],
    check: ok("2026-10-18T09:12:00+08:00", 9),
    trial: passed("2026-10-17T22:15:00+08:00", 24, 9.6),
    created_at: "2026-10-17T22:02:00+08:00",
    updated_at: "2026-10-18T09:12:00+08:00",
  },
  {
    id: "wf_wan",
    slug: "wan22-i2v",
    model_key: "comfy/wan22-i2v",
    name: "Wan 2.2 图生视频（社区）",
    tier: "unverified",
    source: "user",
    origin: "video_wan2_2_14B_i2v.json",
    components: ["vid"],
    caps: { aspects: ["9:16", "16:9", "1:1"], max_seconds: 5, refs: null, vram_gb: 24 },
    file_sha256: "7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b",
    file_changed: false,
    uses_dramastudio_nodes: false,
    bindings: [
      bind("first_frame", "Load Image", "LoadImage", "image", "guessed"),
      bind("prompt", "Positive Prompt", "CLIPTextEncode", "text"),
      bind("negative", "Negative Prompt", "CLIPTextEncode", "text"),
      bind("width", "WanImageToVideo", "WanImageToVideo", "width"),
      bind("height", "WanImageToVideo", "WanImageToVideo", "height"),
      bind("seed", "KSampler (high noise)", "KSamplerAdvanced", "noise_seed", "guessed"),
      bind("fps", "Create Video", "CreateVideo", "fps", "guessed"),
      bind("video_out", "Save Video", "SaveVideo", null),
    ],
    nodes: WAN_NODES,
    check: ok("2026-10-18T09:20:00+08:00", 11),
    trial: null,
    created_at: "2026-10-18T09:20:00+08:00",
    updated_at: "2026-10-18T09:20:00+08:00",
  },
  {
    id: "wf_kontext",
    slug: "flux-kontext-kf",
    model_key: "comfy/flux-kontext-kf",
    name: "Flux Kontext 关键帧（社区）",
    tier: "unverified",
    source: "user",
    origin: "flux_kontext_dev_gguf.json",
    components: ["kf"],
    caps: { aspects: ["9:16", "16:9", "3:4", "1:1"], max_seconds: null, refs: 2, vram_gb: 16 },
    file_sha256: "3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c",
    file_changed: false,
    uses_dramastudio_nodes: false,
    bindings: [
      bind("ref_image", "参考图 1", "LoadImage", "image", "confirmed", 1),
      bind("ref_image", "参考图 2", "LoadImage", "image", "confirmed", 2),
      bind("prompt", "Prompt", "CLIPTextEncode", "text"),
      bind("width", "Empty Latent", "EmptySD3LatentImage", "width"),
      bind("height", "Empty Latent", "EmptySD3LatentImage", "height"),
      bind("seed", "Seed", "Seed (rgthree)", "seed"),
      bind("image_out", "Save Image", "SaveImage", null),
    ],
    nodes: [
      node("参考图 1", "LoadImage", ["image"]),
      node("参考图 2", "LoadImage", ["image"]),
      node("Prompt", "CLIPTextEncode", ["text"]),
      node("Empty Latent", "EmptySD3LatentImage", ["width", "height", "batch_size"]),
      node("Unet Loader (GGUF)", "UnetLoaderGGUF", ["unet_name"]),
      node("Seed", "Seed (rgthree)", ["seed"]),
      node("Save Image", "SaveImage", ["filename_prefix"]),
    ],
    check: {
      at: "2026-10-18T09:25:00+08:00",
      status: "missing",
      node_classes: { found: 17, total: 19 },
      missing_packs: [
        {
          name: "ComfyUI-GGUF",
          classes: ["UnetLoaderGGUF"],
          source: "registry",
          version: "1.1.4",
          url: "https://github.com/city96/ComfyUI-GGUF",
        },
        {
          name: "rgthree-comfy",
          classes: ["Seed (rgthree)"],
          source: "registry",
          version: "1.0.2",
          url: "https://github.com/rgthree/rgthree-comfy",
        },
      ],
      missing_models: [
        {
          folder: "unet",
          name: "flux1-kontext-dev-Q8_0.gguf",
          size_bytes: 12_700_000_000,
          url: "https://huggingface.co/QuantStack/FLUX.1-Kontext-dev-GGUF",
        },
      ],
      problems: [],
    },
    trial: null,
    created_at: "2026-10-18T09:25:00+08:00",
    updated_at: "2026-10-18T09:25:00+08:00",
  },
];

/** ComfyUI's own workflow list (its user data folder), to import from. */
export const comfyWorkflowFiles: ComfyWorkflowFile[] = [
  {
    path: "我的/口型-latentsync.json",
    modified_at: "2026-10-17T21:58:00+08:00",
    imported_as: "wf_latentsync",
    board: false,
  },
  {
    path: "video_wan2_2_14B_i2v.json",
    modified_at: "2026-10-18T09:18:00+08:00",
    imported_as: "wf_wan",
    board: false,
  },
  {
    path: "flux_kontext_dev_gguf.json",
    modified_at: "2026-10-18T09:24:00+08:00",
    imported_as: "wf_kontext",
    board: false,
  },
  {
    path: "我的/雨夜氛围-ltx2.json",
    modified_at: "2026-10-16T23:40:00+08:00",
    imported_as: null,
    board: false,
  },
  {
    path: "hunyuan_video_t2v_720p.json",
    modified_at: "2026-10-12T20:05:00+08:00",
    imported_as: null,
    board: false,
  },
  {
    path: "短剧/雨停之前/第1集-素材板.json",
    modified_at: "2026-10-18T08:30:00+08:00",
    imported_as: null,
    board: true,
  },
];

/** What importing a new workflow guesses (SPEC 6.4.3): ComfyUI's LTX-2 image-to-video template. */
export const importedGuess = {
  components: ["vid"],
  caps: { aspects: ["9:16", "16:9"], max_seconds: 8, refs: null, vram_gb: 20 },
  nodes: [
    node("Load Image", "LoadImage", ["image"]),
    node("CLIP Text Encode (Positive)", "CLIPTextEncode", ["text"]),
    node("CLIP Text Encode (Negative)", "CLIPTextEncode", ["text"]),
    node("EmptyLTXVLatentVideo", "EmptyLTXVLatentVideo", ["width", "height", "length"]),
    node("RandomNoise", "RandomNoise", ["noise_seed"]),
    node("Create Video", "CreateVideo", ["fps"]),
    node("Save Video", "SaveVideo", ["filename_prefix"]),
  ],
  bindings: [
    bind("first_frame", "Load Image", "LoadImage", "image", "guessed"),
    bind("prompt", "CLIP Text Encode (Positive)", "CLIPTextEncode", "text", "guessed"),
    bind("negative", "CLIP Text Encode (Negative)", "CLIPTextEncode", "text", "guessed"),
    bind("width", "EmptyLTXVLatentVideo", "EmptyLTXVLatentVideo", "width", "guessed"),
    bind("height", "EmptyLTXVLatentVideo", "EmptyLTXVLatentVideo", "height", "guessed"),
    bind("seed", "RandomNoise", "RandomNoise", "noise_seed", "guessed"),
    bind("fps", "Create Video", "CreateVideo", "fps", "guessed"),
    bind("video_out", "Save Video", "SaveVideo", null, "guessed"),
  ],
};

export const TRIAL_DRAFT = DRAFT;
