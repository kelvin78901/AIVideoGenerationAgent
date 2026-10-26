/**
 * Episode 1 assets (prototype Assets.dc.html `assets()`). The assets themselves are the
 * backend's since M3 step 3 (its demo seed has the same 13, 7 locked), and so are the shots
 * that use them since M4; the demo keeps them for the kinds its video QA checks (M5).
 */
import type { Asset } from "@/api/schemas/assets";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

type Seed = Omit<
  Asset,
  | "series_id"
  | "product_id"
  | "status"
  | "pick"
  | "text"
  | "voice"
  | "scenes"
  | "note"
  | "seed_changed"
  | "shots"
> &
  Partial<Pick<Asset, "text" | "voice">> & { state: "locked" | "choosing" | "none" };

const msg = (code: string, params: Record<string, string | number> = {}) => ({ code, params });

const seeds: Seed[] = [
  {
    id: "linwan",
    kind: "character",
    name: "林晚",
    state: "locked",
    source: msg("script_line", { scene: 1, line: 1 }),
    intent:
      "26 岁女性，插画师。米色风衣湿了半边，低马尾，素颜，左手腕一根旧黑发圈。神情疲惫但克制。",
  },
  {
    id: "zhouyu",
    kind: "character",
    name: "周屿",
    state: "none",
    source: msg("script_line_note", { scene: 1, line: 3, note: "本集只出现字迹" }),
    intent: "外貌待定，第 2 集出场前再做。",
  },
  {
    id: "hall",
    kind: "scene",
    name: "老小区楼道 · 夜",
    state: "locked",
    source: msg("scene_heading", { scene: 1 }),
    intent: "六层老楼的楼道，水泥台阶，墙皮剥落；声控灯偏黄，坏了一半；窗外下大雨，地上有湿脚印。",
  },
  {
    id: "room",
    kind: "scene",
    name: "林晚出租屋 · 夜",
    state: "choosing",
    source: msg("scene_heading", { scene: 2 }),
    intent: "十来平米的出租屋，门后挂着画板，桌上堆着画稿；只开一盏台灯，暖光；旧的绿色铁门。",
  },
  {
    id: "store",
    kind: "scene",
    name: "楼下便利店 · 夜",
    state: "none",
    source: msg("episode_scene", { episode: 2, scene: 3 }),
    intent: "第 2 集才出现，到时再做。",
  },
  {
    id: "umbrella",
    kind: "prop",
    name: "红色长柄伞",
    state: "locked",
    source: msg("script_line", { scene: 1, line: 2 }),
    intent: "正红色长柄直伞，木质弯柄，伞面是湿的，收着靠墙。",
  },
  {
    id: "note",
    kind: "prop",
    name: "黄色便利贴",
    state: "locked",
    source: msg("script_line", { scene: 1, line: 2 }),
    intent: "方形黄色便利贴，贴在伞柄上，边角被雨打湿卷起。上面的字另做（见画面文字）。",
  },
  {
    id: "band",
    kind: "prop",
    name: "旧黑发圈",
    state: "choosing",
    source: msg("script_line", { scene: 1, line: 4 }),
    intent: "洗旧了的黑色布发圈，戴在林晚左手腕上。",
  },
  {
    id: "phone",
    kind: "prop",
    name: "手机",
    state: "locked",
    source: msg("script_line", { scene: 2, line: 2 }),
    intent: "普通全面屏手机，黑色壳，屏幕有一道细划痕。锁屏内容另做（见画面文字）。",
  },
  {
    id: "txt1",
    kind: "text",
    name: "便利贴手写",
    state: "choosing",
    source: msg("script_line", { scene: 1, line: 3 }),
    intent: "黑色圆珠笔手写，字迹歪扭但能认清，写在黄色便利贴上。",
    text: { exact: "楼下便利店，等你到十二点。", method: "model", style: "handwritten" },
  },
  {
    id: "txt2",
    kind: "text",
    name: "手机锁屏时间",
    state: "locked",
    source: msg("script_line", { scene: 2, line: 2 }),
    intent: "手机锁屏上的大号时间，白字，系统默认字体，下方没有通知。",
    text: { exact: "23:52", method: "composite", style: "screen" },
  },
  {
    id: "vlinwan",
    kind: "voice",
    name: "林晚",
    state: "locked",
    source: msg("dialogue_count", { count: 2 }),
    intent: "二十多岁女声，偏低，克制，句尾轻，不要播音腔。",
    voice: {
      method: "design",
      lines: [
        { text: "……周屿？", tone: "低声，愣住" },
        { text: "三年了。他凭什么。", tone: "画外音，压着火" },
      ],
    },
  },
  {
    id: "vzhouyu",
    kind: "voice",
    name: "周屿",
    state: "none",
    source: msg("episode", { episode: 2 }),
    intent: "第 2 集出场前再定。",
    voice: { method: "design", lines: [] },
  },
];

export const assets: Asset[] = seeds.map(({ id, kind, name, intent, source, text, voice }) => ({
  id,
  kind,
  name,
  intent,
  source,
  shots: [],
  series_id: DEMO_SERIES_ID,
  product_id: `demo-p-asset-${id}`,
  scenes: [],
  status: "not_generated",
  pick: 0,
  text: text ?? null,
  voice: voice ?? null,
  note: null,
  seed_changed: false,
}));
