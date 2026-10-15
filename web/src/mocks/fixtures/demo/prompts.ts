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
  script:
    "把叙述改成能拍的剧本：场景头（场次、日夜、内外、地点）、动作（△）、台词（人物和语气）。心理活动尽量变成动作或画外音（OS）。原文没有的台词标为 AI 新增，宁少勿多。",
};

const templates: Record<string, (intent: string) => string> = {
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
