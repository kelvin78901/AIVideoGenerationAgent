/**
 * 《雨停之前》: 4 enrichment suggestions on chapter 1 (prototype Main.dc.html `renderVals()`,
 * the first one adopted). The novel and its bible come from the backend (seeded in Mock mode
 * from `tests/fixtures/demo/`); chapter 1 as the backend answers it is in `test/data/novel.json`,
 * so the offsets of these anchors and of the demo script's source spans point at its text.
 */
import { NovelSchema, type Suggestion } from "@/api/schemas/novel";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import data from "@/test/data/novel.json";

export const SOURCE = "demo-src";

/** `GET /series/demo/novel` (chapter 1 《红伞》: paragraphs 01–05). */
export const novel = NovelSchema.parse(data.chapters[0]);

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
