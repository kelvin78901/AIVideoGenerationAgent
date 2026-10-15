/**
 * Sync targets, rules, log and episode 1's ComfyUI board (prototype Sync.dc.html). Shot
 * states on the board match the demo episode: 1-01…1-03 adopted, 1-04 four takes, 1-05
 * generating, 1-06 / 1-07 queued, 1-08 / 1-09 waiting for a tail frame.
 */
import type {
  BoardNode,
  BoardWire,
  SyncBoard,
  SyncLogEntry,
  SyncRules,
  SyncTarget,
} from "@/api/schemas/sync";
import { EP1 } from "@/mocks/fixtures/demo/episodes";

const m = (code: string, params: Record<string, string | number> = {}) => ({ code, params });

export const syncTargets: SyncTarget[] = [
  {
    id: "comfy",
    enabled: true,
    direction: "two_way",
    state: "ok",
    status: m("comfy_ok", { host: "127.0.0.1:8188", pack: "DramaStudio" }),
    mode: null,
    unavailable_modes: {},
  },
  {
    id: "folder",
    enabled: true,
    direction: "one_way",
    state: "ok",
    status: m("folder_ok", { path: "D:\\短剧\\雨停之前\\", free: "1.2 TB" }),
    mode: null,
    unavailable_modes: {},
  },
  {
    id: "eagle",
    enabled: false,
    direction: "one_way",
    state: "missing",
    status: m("eagle_missing"),
    mode: null,
    unavailable_modes: {},
  },
  {
    id: "resolve",
    enabled: true,
    direction: "one_way",
    state: "warn",
    status: m("resolve_free", { version: "21.1" }),
    mode: "fcpxml",
    // Free Resolve dropped external scripting in 21.1 (SPEC 14.4).
    unavailable_modes: { api: m("resolve_needs_studio") },
  },
];

export const syncRules: SyncRules = {
  when: "adopt",
  kinds: ["character", "scene", "prop", "text", "voice", "keyframe", "video_adopted", "dub"],
  org: "shot",
  extras: ["prompt", "model_cost", "qa"],
};

export const SYNC_ROOT = "D:\\短剧\\雨停之前\\";

const at = (hm: string) => `2026-10-14T${hm}:00+08:00`;

export const syncLog: SyncLogEntry[] = [
  {
    id: "sl6",
    at: at("11:48"),
    what: m("ingest", { shot: "1-06", n: 3, model: "Qwen-Image-Edit" }),
    to: [m("history", { shot: "1-06" })],
  },
  {
    id: "sl5",
    at: at("11:20"),
    what: m("upscaled", { from: "1-01", to: "1-03", model: "SeedVR2" }),
    to: [m("folder"), m("resolve_replaced")],
  },
  {
    id: "sl4",
    at: at("11:19"),
    what: m("adopted", { shot: "1-03", n: 2 }),
    to: [m("comfy"), m("folder")],
  },
  {
    id: "sl3",
    at: at("11:13"),
    what: m("adopted", { shot: "1-02", n: 2 }),
    to: [m("comfy"), m("folder")],
  },
  {
    id: "sl2",
    at: at("11:06"),
    what: m("adopted", { shot: "1-01", n: 2 }),
    to: [m("comfy"), m("folder")],
  },
  {
    id: "sl1",
    at: at("10:44"),
    what: m("locked", { names: "林晚、周屿、楼道、出租屋、红伞、便利贴、林晚音色" }),
    to: [m("comfy"), m("folder"), m("eagle_missing")],
  },
];

/** A manual run in the demo: files checked and how many were new (prototype: 24, 3 new). */
export const SYNC_RUN = { total: 24, added: 3 };

// ---- board ----

type Fact = [key: string, value: string];
const facts = (list: Fact[]) => list.map(([key, value]) => ({ key, value }));

function thumb(
  id: string,
  x: number,
  y: number,
  title: string,
  caption: ReturnType<typeof m>,
  tone: BoardNode["tone"],
  shade: number,
  info: Fact[],
  { small = false, dashed = false, kind = "image" as BoardNode["kind"] } = {},
): BoardNode {
  return {
    id,
    kind,
    title,
    caption,
    tone,
    thumb: { shade, dashed, small },
    text: null,
    rows: [],
    facts: facts(info),
    x,
    y,
    w: small ? 64 : 84,
    h: small ? 162 : 176,
  };
}

const shot = (
  id: string,
  x: number,
  y: number,
  title: string,
  caption: ReturnType<typeof m>,
  tone: BoardNode["tone"],
  shade: number,
  info: Fact[],
  dashed = false,
) => thumb(id, x, y, title, caption, tone, shade, info, { small: true, dashed, kind: "video" });

function plain(
  id: string,
  kind: "audio" | "note" | "func",
  box: [x: number, y: number, w: number, h: number],
  title: string,
  info: Fact[],
  extra: Partial<BoardNode> = {},
): BoardNode {
  const [x, y, w, h] = box;
  return {
    id,
    kind,
    title,
    caption: null,
    tone: null,
    thumb: null,
    text: null,
    rows: [],
    facts: facts(info),
    x,
    y,
    w,
    h,
    ...extra,
  };
}

type Row = BoardNode["rows"][number];
const out = (label: string, type: Row["type"]): Row => ({ label, dir: "out", type });
const inp = (label: string, type: Row["type"]): Row => ({ label, dir: "in", type });
const widget = (label: string): Row => ({ label, dir: "widget", type: null });

/** The size row reads the output spec (CLAUDE.md rule 10); the handler fills it in. */
export const SIZE_ROW = { node: "ds1", row: 6 };

const nodes: BoardNode[] = [
  thumb("lw1", 36, 58, "林晚 · 正面", m("locked", { n: 2 }), "ok", 1, [
    ["file", "E01/角色/林晚/林晚_正面_v2.png"],
    ["model", "Nano Banana Pro · $0.14"],
    ["used_in", "1-01、1-04、1-05、1-06"],
  ]),
  thumb("lw2", 128, 58, "林晚 · 侧面", m("filled_after_lock"), "ok", 1, [
    ["file", "E01/角色/林晚/林晚_侧面_v1.png"],
    ["source", "锁定正面后自动补齐"],
  ]),
  thumb("zy1", 220, 58, "周屿 · 字迹", m("locked", { n: 1 }), "ok", 4, [
    ["file", "E01/角色/周屿/周屿_字迹_v1.png"],
    ["note", "本集只出现字迹"],
  ]),
  plain("vc1", "audio", [36, 244, 268, 44], "音色 · 林晚（平静）· 已锁定", [
    ["file", "E01/音色/林晚_平静_v1.wav"],
    ["model", "MiniMax 音色设计 · $3.00"],
    ["variants", "平静、哭腔、耳语"],
  ]),
  thumb("sc1", 356, 58, "楼道 · 夜", m("locked", { n: 1 }), "ok", 2, [
    ["file", "E01/场景/楼道_夜_v1.png"],
    ["used_in", "场 1 全部 5 镜"],
  ]),
  thumb("sc2", 448, 58, "出租屋 · 夜", m("locked", { n: 1 }), "ok", 4, [
    ["file", "E01/场景/出租屋_夜_v1.png"],
    ["used_in", "场 2 全部 4 镜"],
  ]),
  thumb("pp1", 540, 58, "红色长柄伞", m("locked", { n: 1 }), "ok", 3, [
    ["file", "E01/道具/红伞_v1.png"],
    ["used_in", "1-02、1-09"],
  ]),
  plain(
    "tx1",
    "note",
    [356, 244, 268, 44],
    "画面文字 · 便利贴",
    [
      ["file", "E01/画面文字/便利贴_v2.png"],
      ["model", "GPT Image 2 · $0.28 × 2"],
      ["check", "OCR 逐字一致"],
    ],
    { text: "「十二点前，伞还在门口，我就回来。」逐字核对 · GPT Image 2" },
  ),
  shot("kf101", 676, 58, "1-01", m("adopted", { n: 2 }), "ok", 2, [
    ["file", "E01/S01/1-01/E01_S01_1-01_video_v2.mp4"],
    ["model", "H3 API 终版 · $0.32"],
    ["qa", "通过"],
  ]),
  shot("kf102", 748, 58, "1-02", m("adopted", { n: 2 }), "ok", 3, [
    ["file", "E01/S01/1-02/E01_S01_1-02_video_v2.mp4"],
    ["model", "H3 API 终版 · $0.24"],
    ["qa", "通过（草稿伞色偏橙没过）"],
  ]),
  shot("kf103", 820, 58, "1-03", m("adopted", { n: 2 }), "ok", 2, [
    ["file", "E01/S01/1-03/E01_S01_1-03_video_v2.mp4"],
    ["model", "H3 API 终版 · $0.24"],
    ["qa", "画面文字逐字一致"],
    ["upscale", "SeedVR2 本地精修"],
  ]),
  shot("kf104", 892, 58, "1-04", m("picking", { count: 4 }), "pending", 1, [
    ["file", "E01/S01/1-04/（T1–T4 共 4 条）"],
    ["status", "还没采纳，最好的 T3 人脸 0.82"],
    ["cost", "$1.96"],
  ]),
  shot("kf105", 964, 58, "1-05", m("generating"), "running", 1, [
    ["file", "E01/S01/1-05/E01_S01_1-05_kf_v1.png"],
    ["status", "本地 H3 正在出 T1"],
  ]),
  plain(
    "nt1",
    "note",
    [676, 232, 352, 56],
    "便签 · 场 1",
    [["source", "自动生成，跟随剧本和路由更新"]],
    {
      text: "雨夜 23:40 前后 · 楼道（六楼）· 关键帧 Nano Banana Pro · 视频本地 H3 草稿 → H3 API 终版",
    },
  ),
  shot("kf106", 36, 358, "1-06", m("keyframe_pending", { n: 3 }), "pending", 4, [
    ["file", "E01/S02/1-06/E01_S02_1-06_kf_v3.png"],
    ["source", "ComfyUI 存回（Qwen-Image-Edit 局部重绘）"],
    ["cost", "本地，无 API 费用"],
  ]),
  shot("kf107", 108, 358, "1-07", m("queued"), "waiting", 4, [
    ["file", "E01/S02/1-07/E01_S02_1-07_kf_v1.png"],
    ["status", "关键帧已出，等本地队列"],
  ]),
  shot(
    "kf108",
    180,
    358,
    "1-08",
    m("waiting_for", { shot: "1-06" }),
    "waiting",
    0,
    [["status", "首帧接 1-06 的尾帧，等 1-06 采纳"]],
    true,
  ),
  shot(
    "kf109",
    252,
    358,
    "1-09",
    m("waiting_for", { shot: "1-08" }),
    "waiting",
    0,
    [["status", "首帧接 1-08 的尾帧"]],
    true,
  ),
  plain(
    "ds1",
    "func",
    [356, 362, 200, 200],
    "DramaStudio ▸ 镜头",
    [
      ["role", "从工作台读这个镜头已锁定的关键帧、台词音频、参考图和提示词"],
      ["size", "跟随成片规格"],
    ],
    {
      rows: [
        widget("镜头：1-04 ▾"),
        widget("版本：已锁定"),
        out("关键帧", "image"),
        out("台词音频", "audio"),
        out("参考图 ×3", "image"),
        out("提示词", "prompt"),
        out("", "size"),
        out("时长 4.0 秒", "size"),
      ],
    },
  ),
  plain(
    "h3",
    "func",
    [596, 362, 200, 200],
    "MiniMax H3 图生视频",
    [["note", "你自己的工作流节点，平台不改它"]],
    {
      rows: [
        inp("首帧", "image"),
        inp("音频", "audio"),
        inp("参考", "image"),
        inp("提示词", "prompt"),
        inp("尺寸", "size"),
        out("视频", "video"),
        widget("步数 8 · Turbo LoRA"),
      ],
    },
  ),
  plain(
    "sv",
    "func",
    [836, 362, 190, 200],
    "DramaStudio ▸ 存回工作台",
    [
      ["role", "把结果存成 1-04 的新候选 T5，进历史、跑质检、记调用（本地为 0）"],
      ["never", "覆盖已采纳的版本"],
    ],
    {
      rows: [
        inp("视频", "video"),
        widget("存为：1-04 新候选"),
        widget("来源：ComfyUI 本地"),
        widget("自动质检：开"),
      ],
    },
  ),
];

const wire = (from: string, fr: number, to: string, tr: number, type: BoardWire["type"]) => ({
  from: { node: from, row: fr },
  to: { node: to, row: tr },
  type,
});

export const syncBoard: SyncBoard = {
  episode_id: EP1,
  width: 1060,
  height: 640,
  comfy_url: "http://127.0.0.1:8188/",
  groups: [
    { id: "g-cast", title: m("cast"), color: "#4B6A9B", x: 20, y: 20, w: 300, h: 280 },
    { id: "g-world", title: m("world"), color: "#3F7A62", x: 340, y: 20, w: 300, h: 280 },
    {
      id: "g-s1",
      title: m("scene", { n: 1, heading: "老小区楼道", shots: 5 }),
      color: "#6E5A98",
      x: 660,
      y: 20,
      w: 380,
      h: 280,
    },
    {
      id: "g-s2",
      title: m("scene", { n: 2, heading: "林晚出租屋", shots: 4 }),
      color: "#6E5A98",
      x: 20,
      y: 320,
      w: 300,
      h: 300,
    },
    {
      id: "g-work",
      title: m("workflow", { shot: "1-04" }),
      color: "#8A6A2E",
      x: 340,
      y: 320,
      w: 700,
      h: 300,
    },
  ],
  nodes,
  wires: [
    wire("ds1", 2, "h3", 0, "image"),
    wire("ds1", 3, "h3", 1, "audio"),
    wire("ds1", 4, "h3", 2, "image"),
    wire("ds1", 5, "h3", 3, "prompt"),
    wire("ds1", 6, "h3", 4, "size"),
    wire("h3", 5, "sv", 0, "video"),
  ],
};
