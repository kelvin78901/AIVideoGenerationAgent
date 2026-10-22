/**
 * Episode 1 shots (prototype Storyboard.dc.html `shots()`): 9 shots, 34 s, 3 confirmed. Each
 * non-continuous shot has a keyframe product with 3 candidates; 1-08 and 1-09 take an
 * earlier shot's last frame instead (1-08 skips the insert 1-07 and continues 1-06).
 */
import type { Product, ProductVersion } from "@/api/schemas/products";
import type { BlockingItem, Framing, Shot } from "@/api/schemas/shots";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { demoAt, demoVersion } from "@/mocks/fixtures/demo/products";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

export const PRODUCT_PLAN = "demo-p-plan-e1";
export const shotId = (label: string) => `demo-shot-${label}`;
const kfProductId = (label: string) => `demo-p-kf-${label}`;
/** Video takes for the shot (fixtures/demo/takes.ts). */
export const videoProductId = (label: string) => `demo-p-vid-${label}`;

const CAMERA: Record<Framing, [number, number]> = {
  wide: [0.5, 0.92],
  medium: [0.5, 0.8],
  close: [0.38, 0.7],
  closeup: [0.55, 0.62],
};

function blocking(room: boolean, framing: Framing): BlockingItem[] {
  const [cx, cy] = CAMERA[framing];
  const camera: BlockingItem = { id: "camera", kind: "camera", label: "", x: cx, y: cy };
  return room
    ? [
        { id: "door", kind: "landmark", label: "门", x: 0.5, y: 0.12 },
        { id: "desk", kind: "landmark", label: "桌", x: 0.82, y: 0.45 },
        { id: "linwan", kind: "character", label: "林晚", x: 0.5, y: 0.3 },
        camera,
      ]
    : [
        { id: "stairs", kind: "landmark", label: "楼梯", x: 0.14, y: 0.7 },
        { id: "door", kind: "landmark", label: "家门", x: 0.78, y: 0.14 },
        { id: "umbrella", kind: "prop", label: "红伞", x: 0.9, y: 0.36 },
        { id: "linwan", kind: "character", label: "林晚", x: 0.62, y: 0.4 },
        camera,
      ];
}

type Seed = Pick<
  Shot,
  "summary" | "intent" | "shot_type" | "framing" | "camera_move" | "duration_s" | "dialogue"
> &
  Partial<Pick<Shot, "sound" | "audio_mode" | "tail_from" | "tail_note" | "confirmed">> & {
    label: string;
    /** The script lines it films (fixture ids, as the backend's demo script). */
    lines: string[];
    scene: 1 | 2;
    place: string;
    assets: string[];
  };

const seeds: Seed[] = [
  {
    label: "1-01",
    lines: ["demo-b2"],
    scene: 1,
    place: "老小区楼道 · 六楼家门口",
    shot_type: "scene_change",
    framing: "wide",
    camera_move: "push",
    duration_s: 4,
    confirmed: true,
    summary: "楼道全景，林晚走上六楼",
    intent: "楼道全景，声控灯忽明忽暗，林晚抱着画板袋走上六楼。",
    dialogue: null,
    sound: "雨声、脚步、灯的电流声",
    assets: ["linwan", "hall"],
  },
  {
    label: "1-02",
    lines: ["demo-b3"],
    scene: 1,
    place: "老小区楼道 · 六楼家门口",
    shot_type: "same_scene_cut",
    framing: "medium",
    camera_move: "static",
    duration_s: 3,
    confirmed: true,
    summary: "门口的红伞和便利贴",
    intent: "门口：红色长柄伞斜靠在墙边，伞柄上贴着黄色便利贴。",
    dialogue: null,
    assets: ["hall", "umbrella", "note"],
  },
  {
    label: "1-03",
    lines: ["demo-b4"],
    scene: 1,
    place: "老小区楼道 · 六楼家门口",
    shot_type: "same_scene_cut",
    framing: "closeup",
    camera_move: "static",
    duration_s: 3,
    confirmed: true,
    summary: "便利贴上的字",
    intent: "便利贴特写，歪扭的手写字，边角被雨打湿。",
    dialogue: null,
    assets: ["note", "txt1"],
  },
  {
    label: "1-04",
    lines: ["demo-b5"],
    scene: 1,
    place: "老小区楼道 · 六楼家门口",
    shot_type: "same_scene_cut",
    framing: "close",
    camera_move: "push",
    duration_s: 4,
    summary: "林晚愣住：……周屿？",
    intent: "林晚低头看着便利贴，愣住，低声说话。声控灯在她脸上一明一暗。",
    dialogue: "林晚（低声，愣住）：……周屿？",
    assets: ["linwan", "hall", "vlinwan"],
  },
  {
    label: "1-05",
    lines: ["demo-b6"],
    scene: 1,
    place: "老小区楼道 · 六楼家门口",
    shot_type: "same_scene_cut",
    framing: "closeup",
    camera_move: "static",
    duration_s: 3,
    summary: "指尖、旧发圈",
    intent: "她的指尖停在便利贴上，下意识摸左手腕的旧发圈。",
    dialogue: null,
    assets: ["linwan", "note", "band"],
  },
  {
    label: "1-06",
    lines: ["demo-b8", "demo-b10"],
    scene: 2,
    place: "林晚出租屋",
    shot_type: "scene_change",
    framing: "medium",
    camera_move: "static",
    duration_s: 5,
    audio_mode: "tts",
    summary: "背靠着门，画外音",
    intent: "出租屋内，她进门、关门，后背抵着门，台灯暖光。",
    dialogue: "林晚（画外音）：三年了。他凭什么。",
    assets: ["linwan", "room", "vlinwan"],
  },
  {
    label: "1-07",
    lines: ["demo-b9"],
    scene: 2,
    place: "林晚出租屋",
    shot_type: "same_scene_cut",
    framing: "closeup",
    camera_move: "static",
    duration_s: 2,
    summary: "手机亮屏 23:52",
    intent: "手机亮屏，锁屏时间 23:52，没有新消息。",
    dialogue: null,
    assets: ["phone", "txt2"],
  },
  {
    label: "1-08",
    lines: ["demo-b11"],
    scene: 2,
    place: "林晚出租屋",
    shot_type: "continuous",
    framing: "medium",
    camera_move: "static",
    duration_s: 6,
    summary: "开门，关门，再开门",
    intent: "她拉开门，又关上；停两秒，再拉开。",
    dialogue: null,
    sound: "门轴声、雨声",
    tail_from: "1-06",
    tail_note: "中间的 1-07 是插入镜头，所以接的是 1-06，不是上一个镜头。",
    assets: ["linwan", "room"],
  },
  {
    label: "1-09",
    lines: ["demo-b12"],
    scene: 2,
    place: "林晚出租屋",
    shot_type: "continuous",
    framing: "close",
    camera_move: "push",
    duration_s: 4,
    summary: "她拿起了那把伞（卡点）",
    intent: "门外，她弯腰拿起那把红伞，最后一帧定格。",
    dialogue: null,
    sound: "卡点音效",
    tail_from: "1-08",
    tail_note: "最后一帧定格做卡点，后期加音效。",
    assets: ["linwan", "umbrella", "hall"],
  },
];

const KF_LABELS = ["构图偏左，留门的位置", "居中，灯光更暗", "低机位，压迫感更强"];
export const keyframeCandidates = () => ({ candidates: KF_LABELS.map((label) => ({ label })) });

function keyframeVersions(seed: Seed, productId: string): ProductVersion[] {
  if (seed.shot_type === "continuous") return [];
  const v = (n: number, model: string, at: string, parent: string | null = null) =>
    demoVersion(productId, "kf", {
      n,
      origin: "run",
      model,
      at: demoAt(at),
      parent,
      intent: seed.intent,
      payload: keyframeCandidates(),
    });
  if (!seed.confirmed) return [v(1, "comfy/qwen-image-edit", "11:06")];
  // 混合: 本地草稿, then the API final once adopted.
  const draft = v(1, "comfy/qwen-image-edit", "10:55");
  return [draft, v(2, "google/nano-banana-pro", "11:02", draft.id)];
}

function keyframeProduct(seed: Seed): Product {
  const id = kfProductId(seed.label);
  const versions = keyframeVersions(seed, id);
  const last = versions.at(-1);
  const adopted = seed.confirmed ? last : undefined;
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: "shot",
    owner_id: shotId(seed.label),
    slot: "keyframe",
    component_id: "kf",
    current_version_id: last?.id ?? null,
    adopted_version_id: adopted?.id ?? null,
    locked_hash: null,
    status: adopted ? "adopted" : last ? "ready" : "empty",
    versions,
    prompt: null,
    estimate: null,
    running: null,
  };
}

export const shots: Shot[] = seeds.map((s, i) => ({
  id: shotId(s.label),
  episode_id: EP1,
  scene_id: s.scene === 1 ? "demo-b1" : "demo-b7",
  label: s.label,
  scene_no: s.scene,
  scene_place: s.place,
  idx: i + 1,
  summary: s.summary,
  line_ids: s.lines,
  intent: s.intent,
  seed_changed: false,
  shot_type: s.shot_type,
  framing: s.framing,
  camera_move: s.camera_move,
  duration_s: s.duration_s,
  duration_source: s.dialogue ? "audio" : "manual",
  min_s: 0,
  planned_s: s.duration_s,
  manual_s: null,
  longest_s: 15,
  split_hint: false,
  dialogue: s.dialogue,
  sound: s.sound ?? null,
  audio_mode: s.audio_mode ?? "native",
  asset_ids: s.assets,
  tail_from: s.tail_from ?? null,
  tail_note: s.tail_note ?? null,
  blocking: blocking(s.scene === 2 && s.label !== "1-09", s.framing),
  keyframe_product_id: kfProductId(s.label),
  video_product_id: videoProductId(s.label),
  keyframe_pick: 0,
  confirmed: s.confirmed ?? false,
}));

const planV1 = demoVersion(PRODUCT_PLAN, "plan", {
  n: 1,
  origin: "run",
  model: "deepseek/v4-pro",
  at: demoAt("10:48"),
  payload: { shots: 9, seconds: 34 },
});

export const shotProducts: Product[] = [
  ...seeds.map(keyframeProduct),
  {
    id: PRODUCT_PLAN,
    series_id: DEMO_SERIES_ID,
    owner_type: "episode",
    owner_id: EP1,
    slot: "shot_plan",
    component_id: "plan",
    current_version_id: planV1.id,
    adopted_version_id: planV1.id,
    locked_hash: null,
    status: "adopted",
    versions: [planV1],
    prompt: null,
    estimate: null,
    running: null,
  },
];
