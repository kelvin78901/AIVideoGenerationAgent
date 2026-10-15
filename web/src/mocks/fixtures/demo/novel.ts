/**
 * 《雨停之前》 opening (prototype Main.dc.html `renderVals()`): 5 paragraphs, 4 enrichment
 * suggestions (the first one adopted), and the extracted bible: 2 characters, 3 locations,
 * 4 props, 2 timeline points.
 */
import type { BibleEntity, Novel, Suggestion } from "@/api/schemas/novel";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

const SOURCE = "demo-src";

const texts = [
  "那天雨下得很大。林晚加完班回到老小区，一层一层爬上六楼。",
  "家门口靠着一把红色的长柄伞，伞柄上贴着一张便利贴。她认得那个字迹。三年了，周屿的字还是歪歪扭扭的，像他这个人一样不靠谱。",
  "便利贴上只写了一句话：“楼下便利店，等你到十二点。”",
  "她把伞靠在墙边，进了屋，又出来，又进去。",
  "最后，她还是拿起了那把伞。",
];

let offset = 0;
export const novel: Novel = {
  series_id: DEMO_SERIES_ID,
  source: { id: SOURCE, filename: "雨停之前.txt", sha256: "sha256:demo-novel" },
  paragraphs: texts.map((text, idx) => {
    const start = offset;
    offset += text.length + 1;
    return { idx, text, start, end: start + text.length };
  }),
};

function suggestion(
  id: string,
  kind: Suggestion["kind"],
  para: number,
  reason: string,
  text: string,
  status: Suggestion["status"] = "pending",
): Suggestion {
  const p = novel.paragraphs[para];
  return {
    id,
    series_id: DEMO_SERIES_ID,
    kind,
    para_idx: para,
    anchor_span: { source_id: SOURCE, start: p?.start ?? 0, end: p?.end ?? 0 },
    reason,
    text,
    status,
    rewrite_instruction: null,
    rewritten_by: null,
  };
}

export const suggestions: Suggestion[] = [
  suggestion(
    "s1",
    "appearance",
    0,
    "林晚第一次出场没有外貌和穿着。后面做角色参考图要靠这一句。",
    "她的米色风衣湿了半边，头发随手扎着，肩上挎着装画板的帆布袋。",
    "accepted",
  ),
  suggestion(
    "s2",
    "lighting",
    0,
    "“雨下得很大”拍不出楼道里的光。补一个看得见的光源，夜戏才有氛围。",
    "楼道的声控灯坏了一半，随着她的脚步忽明忽暗。",
  ),
  suggestion(
    "s3",
    "inner_to_action",
    1,
    "“她认得那个字迹”是心理活动，镜头拍不到。换成一个看得见的小动作。",
    "她的指尖停在便利贴上，下意识摸了摸左手腕上那根旧发圈。",
  ),
  suggestion(
    "s4",
    "cliffhanger",
    3,
    "这段犹豫适合做第 1 集的结尾卡点。加一个看得见时间的特写，观众会知道只剩 8 分钟。",
    "手机屏幕亮了一下：23:52。",
  ),
];

/** What 「按要求重写这一条」 returns in the demo (prototype `alt`). */
export const suggestionRewrites: Record<string, string> = {
  s1: "她裹着一件湿透的工装外套，低马尾有点散，怀里护着一个帆布画板袋。",
  s2: "六楼的声控灯接触不良，她每跺一下脚，灯就闪一下。",
  s3: "她盯着那行字看了很久，拇指一遍遍蹭过左手腕上的旧发圈。",
  s4: "她低头看手机，锁屏上的时间跳到了 23:52。",
};

function entity(
  id: string,
  kind: BibleEntity["kind"],
  name: string,
  summary?: string,
): BibleEntity {
  return {
    id,
    series_id: DEMO_SERIES_ID,
    kind,
    name,
    aliases: [],
    data: summary ? { summary } : {},
    source_spans: [],
    frozen: false,
  };
}

export const bible: BibleEntity[] = [
  entity("c-linwan", "character", "林晚", "26 岁 · 插画师"),
  entity("c-zhouyu", "character", "周屿", "本集只出现字迹"),
  entity("l-stairs", "location", "老小区楼道（六楼）"),
  entity("l-flat", "location", "林晚出租屋"),
  entity("l-store", "location", "楼下便利店"),
  entity("p-umbrella", "prop", "红色长柄伞"),
  entity("p-note", "prop", "便利贴"),
  entity("p-hairtie", "prop", "旧发圈"),
  entity("p-phone", "prop", "手机"),
  entity("e-night", "event", "雨夜 23:40 前后"),
  entity("e-deadline", "event", "约定截止 24:00"),
];
