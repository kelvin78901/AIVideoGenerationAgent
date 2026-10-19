/**
 * Episode 1 script (prototype Script.dc.html `blocksData()`): 2 scenes + 10 lines = 12 段,
 * 2 of them added by AI. `rewrites` is what 「重写这一段」 proposes (prototype `alt`).
 */
import type { Scene, Script, ScriptLine } from "@/api/schemas/script";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { novel, SOURCE } from "@/mocks/fixtures/demo/novel";

const spans = (paras: number[]) =>
  paras.flatMap((i) => {
    const p = novel.paragraphs[i];
    return p ? [{ source_id: SOURCE, start: p.start, end: p.end }] : [];
  });

function scene(id: string, idx: number, heading: string, paras: number[]): Scene {
  return {
    id,
    episode_id: EP1,
    idx,
    heading,
    location_id: null,
    time_of_day: "night",
    source_spans: spans(paras),
    edited: false,
  };
}

let order = 0;
function line(
  id: string,
  sceneId: string,
  type: ScriptLine["type"],
  text: string,
  paras: number[],
  extra: Partial<ScriptLine> = {},
): ScriptLine {
  return {
    id,
    scene_id: sceneId,
    idx: ++order,
    type,
    character_id: null,
    character_name: null,
    tone: null,
    text,
    mood: null,
    duration_s: null,
    overlay_shot: null,
    source_spans: spans(paras),
    ai_added: false,
    cliffhanger: false,
    edited: false,
    ...extra,
  };
}

const SC1 = "demo-b1";
const SC2 = "demo-b7";
const LINWAN = { character_id: "c-linwan", character_name: "林晚" };

const lines1 = [
  line(
    "demo-b2",
    SC1,
    "action",
    "声控灯坏了一半，忽明忽暗。林晚（26，米色风衣湿了半边，挎帆布画板袋）走上六楼。",
    [0],
    { ...LINWAN, mood: "疲惫", duration_s: 4 },
  ),
  line("demo-b3", SC1, "action", "门口靠着一把红色长柄伞，伞柄上贴着一张黄色便利贴。", [1], {
    duration_s: 3,
  }),
  line("demo-b4", SC1, "action", "特写：便利贴，字迹歪扭——“楼下便利店，等你到十二点。”", [2], {
    duration_s: 3,
  }),
  line("demo-b5", SC1, "dialogue", "……周屿？", [1], {
    ...LINWAN,
    tone: "低声，愣住",
    duration_s: 4,
    ai_added: true,
  }),
  line("demo-b6", SC1, "action", "她的指尖停在便利贴上，下意识摸了摸左手腕的旧发圈。", [1], {
    ...LINWAN,
    mood: "动摇",
    duration_s: 3,
  }),
];
order++; // scene 2 heading
const lines2 = [
  line("demo-b8", SC2, "action", "林晚把伞靠回墙边，进屋，关门，背靠着门。", [3], {
    ...LINWAN,
    mood: "强撑",
    duration_s: 5,
  }),
  line("demo-b9", SC2, "action", "特写：手机亮屏，23:52。", [3], { duration_s: 2 }),
  line("demo-b10", SC2, "vo", "三年了。他凭什么。", [1], {
    ...LINWAN,
    tone: "OS",
    overlay_shot: "1-06",
    ai_added: true,
  }),
  line("demo-b11", SC2, "action", "她拉开门，又关上。停了两秒，再拉开。", [3], {
    ...LINWAN,
    mood: "犹豫",
    duration_s: 6,
  }),
  line("demo-b12", SC2, "action", "门外，她拿起了那把伞。", [4], {
    ...LINWAN,
    mood: "下定决心",
    duration_s: 4,
    cliffhanger: true,
  }),
];

export const scripts: Record<string, Script> = {
  [EP1]: {
    episode_id: EP1,
    scenes: [
      scene(SC1, 1, "场 1　夜　内　老小区楼道 · 六楼林晚家门口", [0, 1]),
      scene(SC2, 2, "场 2　夜　内　林晚出租屋", [3]),
    ],
    lines: [...lines1, ...lines2],
  },
};

export const blockRewrites: Record<string, string> = {
  "demo-b1": "场 1　夜　内　老小区六楼楼道",
  "demo-b2": "声控灯一闪一灭。林晚（26，米色风衣湿了半边）抱着帆布画板袋，一步一步走上六楼。",
  "demo-b3": "门边的墙上斜靠着一把红色长柄伞，伞柄上粘着一张黄色便利贴。",
  "demo-b4": "特写：黄色便利贴上一行歪扭的字——“楼下便利店，等你到十二点。”",
  "demo-b5": "……是你啊。",
  "demo-b6": "她的手指在便利贴上停住，又缩回来，攥住了左手腕的旧发圈。",
  "demo-b7": "场 2　夜　内　林晚出租屋 · 门内",
  "demo-b8": "她把伞留在门外，进屋反手关门，后背抵着门板。",
  "demo-b9": "特写：手机锁屏亮起，23:52，没有新消息。",
  "demo-b10": "三年了，一句话就想让我下去？",
  "demo-b11": "她握住门把手，拉开一条缝，又关上。两秒后，再一次拉开。",
  "demo-b12": "她弯下腰，从墙边拿起那把红伞。",
};
