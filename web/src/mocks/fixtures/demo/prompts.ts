/**
 * Demo prompt compiler: what the backend's Jinja templates (SPEC 8) would produce for the novel
 * step's two components. Text is prompt content (sent to the model), not UI copy.
 */
import { modelByKey } from "@/mocks/fixtures/demo/models";

export const intents: Record<string, string> = {
  enrich:
    "保留作者的文风和剧情，只补镜头拍不出来的缺口：人物外貌和穿着、光线和时间、把心理活动改成看得见的动作、每集结尾的卡点。每条建议说明理由。",
  extract:
    "列出所有出场或被提到的人物、地点、道具和时间点。人物写清年龄、职业、外貌。只用原文和已采纳的补写，不要编。",
  split: "每集 1 分钟左右，结尾必须有卡点；第 1 集前 3 秒要有钩子。按原文顺序切，不打乱时间线。",
  plan: "按剧本拆镜头，每个镜头写清类型、景别、时长、首帧怎么来、用哪些参考。总时长贴近目标时长。",
  script:
    "把叙述改成能拍的剧本：场景头（场次、日夜、内外、地点）、动作（△）、台词（人物和语气）。心理活动尽量变成动作或画外音（OS）。原文没有的台词标为 AI 新增，宁少勿多。",
  up: "只提清晰度和细节，不改人物长相、动作和构图。",
  lip: "只改嘴部，保留原有表情和头部动作。",
  music: "钢琴为主，音量压低，雨夜、压抑但不悲；从 1-06 进入，卡点那一下停住。",
  sfx: "老铁门的门轴声要干涩；卡点用一声短促的低频闷响。",
  sub: "每行不超过 14 个字，画外音不加引号，按语气断行。",
  qa: "检查：手和手指有没有畸形、人物有没有变脸、灯光和天气是否符合描述、有没有多余的字。只报问题，不打印象分。",
};

const templates: Record<string, (intent: string) => string> = {
  kf: (intent) =>
    `[任务] 关键帧，3 张候选
[画面] ${intent}
[镜头] {镜头类型、景别、机位运动}
[站位] {站位俯视图}
[参考] {已锁定素材的参考图}
[规格] {成片画幅与分辨率}`,
  vid: (intent) =>
    `[镜头] {镜头号} · {类型} · {景别} · {时长} 秒 · {画幅}
[首帧] {关键帧 或 指定镜头尾帧}
[参考] <Picture 1> {角色} · <Picture 2> {场景} · <Audio 1> {音色}
[画面] ${intent}
[台词] <d>{台词}</d>
[约束] 人物长相与参考一致；不出现字幕和文字`,
  up: (intent) => `[任务] 视频 2K 精修
[输入] 已采纳的 768p 视频
[要求] ${intent}`,
  lip: (intent) =>
    `[任务] 口型修复
[输入] 视频 + 锁定音色配好的台词音频
[要求] ${intent}`,
  qa: (intent) =>
    `[任务] 视频画面检查
[对照] 镜头描述 + 锁定参考图
[要求] ${intent}
[输出 JSON] { "pass": true, "issues": [] }`,
  music: (intent) =>
    `[任务] 短剧配乐
[时长] {从进入的镜头到结尾}
[情绪] ${intent}
[对齐] {卡点镜头的收住时间}
[约束] 不要人声，不要鼓`,
  sfx: (intent) => `[任务] 音效
[位置] {需要补音效的镜头和时间}
[要求] ${intent}`,
  sub: (intent) => `[任务] 字幕对齐
[文字来源] 剧本台词（不改字）
[规则] ${intent}
[输出] SRT`,
  plan: (intent) =>
    `[system]
你负责把剧本拆成镜头。

[规则]
${intent}

[上下文]
{第 1 集剧本}
{已锁定素材}

[输出 JSON]
[{ "id": "1-01", "type": "", "framing": "", "dur": 4, "refs": [] }]`,
  img: (intent) =>
    `[任务] 素材参考图，4 张候选\n[描述] ${intent}\n[风格] 写实电影感，干净背景，均匀柔光，9:16\n[约束] 人物：五官、发型、服装各候选间可不同，但单张内要完整清晰；不要出现任何文字\n[锁定后] 自动补齐侧面、背面和表情`,
  text: (intent) =>
    `[任务] 画面文字素材，4 张候选\n[文字，必须逐字一致] {画面里的字}\n[描述] ${intent}\n[核对] 每张出图后 OCR，与目标文字逐字比对；不一致的标红，不自动采纳`,
  voice: (intent) =>
    `[任务] 音色设计，3 个候选\n[描述] ${intent}\n[试读] 用剧本里该角色的台词，按标注的语气各读一遍\n[约束] 不要播音腔；保留气声和停顿`,
  split: (intent) =>
    "[system]\n你负责给竖屏短剧分集。\n\n[规则]\n" +
    intent +
    '\n\n[上下文]\n{全文摘要 + 段落索引}\n\n[输出 JSON]\n[{ "ep": 1, "title": "", "paras": [1, 5], "hook": "", "cliff": "" }]',
  script: (intent) =>
    "[system]\n你是竖屏短剧编剧。下游是分镜和 AI 视频模型。\n\n[规则]\n" +
    intent +
    '\n- 场景头格式：场次　日/夜　内/外　地点\n- 每段写明 src（原文段号）\n\n[上下文]\n{已确认原文 + 补写}\n{设定卡}\n{分集方案：第 1 集 = 原文第 1–5 段}\n\n[输出 JSON]\n[{ "kind": "scene|action|line|os", "who": "", "paren": "", "text": "", "src": [] }]',
  enrich: (intent) =>
    "[system]\n你是短剧改编编辑。下游是 AI 视频模型，它只能拍到看得见、听得见的东西。\n\n[规则]\n" +
    intent +
    '\n- 不新增人物，不改变事件顺序\n- 每条补写不超过 40 字\n\n[上下文]\n{原文 第 1–5 段}\n{设定卡：林晚、周屿}\n\n[输出 JSON]\n[{ "type": "外貌|光线|心理外化|卡点", "para": 段号, "reason": "…", "insert": "…" }]',
  extract: (intent) =>
    "[system]\n你负责从小说里抽取设定，给剧本和素材步骤使用。\n\n[规则]\n" +
    intent +
    '\n\n[上下文]\n{原文 第 1–5 段 + 已采纳补写}\n\n[输出 JSON]\n{ "人物": [], "地点": [], "道具": [], "时间线": [] }',
};

export function compilePrompt(componentId: string, intent: string, modelKey: string): string {
  const body = (templates[componentId] ?? ((i: string) => `[system]\n${i}`))(intent);
  return `${body}\n\n# 目标模型：${modelByKey(modelKey)?.display ?? modelKey}`;
}
