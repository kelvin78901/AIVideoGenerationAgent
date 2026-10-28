/**
 * Generate step (prototype Generate.dc.html): the auto rules over the candidate wall and the
 * run log. Rule mapping for the backend (M5): `qa_retry_max` is the video component's
 * `fallback.qa_fail_n`, `shot_cap_usd` the `budget` row with scope=shot, `thresholds` the QA
 * component's components.yaml thresholds.
 */
import { z } from "zod";

import { MessageSchema, Timestamp } from "@/api/schemas/common";

export const QaThresholdsSchema = z.object({
  /** Face similarity to the locked reference, ≥. */
  face_sim: z.number(),
  /** SyncNet confidence, ≥. */
  syncnet_conf: z.number(),
  /** ASR character error rate, ≤. */
  cer_max: z.number(),
});
export type QaThresholds = z.infer<typeof QaThresholdsSchema>;

/** `GET / PUT /series/{id}/generate-rules` */
export const GenerateRulesSchema = z.object({
  /** Takes made per shot on the first run. */
  takes_per_shot: z.number().int().min(1).max(6),
  /** Automatic reruns after failed QA before falling back to another model. */
  qa_retry_max: z.number().int().min(0).max(5),
  /** Stop and ask once a shot's spend would pass this. */
  shot_cap_usd: z.number().min(0),
  /** Read-only here; set in components.yaml. */
  thresholds: QaThresholdsSchema,
});
export type GenerateRules = z.infer<typeof GenerateRulesSchema>;

export const GenerateRulesPatchSchema = GenerateRulesSchema.omit({ thresholds: true }).partial();
export type GenerateRulesPatch = z.infer<typeof GenerateRulesPatchSchema>;

/** 按镜头选工作流 (SPEC 6.4.8): a rule's conditions; a field left out matches any shot. */
export const SelectWhenSchema = z.object({
  shot_type: z.enum(["continuous", "same_scene_cut", "scene_change"]).optional(),
  /** 景别 */
  framing: z.enum(["wide", "medium", "close", "closeup"]).optional(),
  /** The shot has lines. */
  dialogue: z.boolean().optional(),
  audio_mode: z.enum(["tts", "native", "none"]).optional(),
  /** A locked reference picture. */
  refs: z.boolean().optional(),
  /** A locked voice sample. */
  voices: z.boolean().optional(),
});
export type SelectWhen = z.infer<typeof SelectWhenSchema>;
export const SELECT_CONDITIONS = [
  "framing",
  "shot_type",
  "dialogue",
  "audio_mode",
  "refs",
  "voices",
] as const satisfies readonly (keyof SelectWhen)[];

export const WorkflowRuleSchema = z.object({
  when: SelectWhenSchema,
  /** A local model key of 视频生成 (one of `models`). */
  model: z.string(),
});
export type WorkflowRule = z.infer<typeof WorkflowRuleSchema>;

/** `GET / PUT / DELETE /series/{id}/workflow-rules`: the first rule a shot meets wins. */
export const WorkflowRulesSchema = z.object({
  rules: z.array(WorkflowRuleSchema),
  /** No rule met: ask the `vselect` LLM before the shot's first take. */
  suggest: z.boolean(),
  /** False: the table from components.yaml (DELETE goes back to it). */
  saved: z.boolean(),
  /** What a rule may name: 平台推荐 and 我的工作流 of 视频生成. */
  models: z.array(z.string()),
});
export type WorkflowRules = z.infer<typeof WorkflowRulesSchema>;
export type WorkflowRulesPut = Pick<WorkflowRules, "rules" | "suggest">;

/**
 * Why a local take went to its workflow: a video version's `params.select`, as its
 * `model_call.select_json`. `rule` is the table's index then; `when` the rule as it was.
 */
export const TakeSelectSchema = z.object({
  by: z.enum(["manual", "rule", "suggest", "default"]),
  rule: z.number().int().optional(),
  when: SelectWhenSchema.optional(),
  reason: z.string().optional(),
  /** The model that suggested it. */
  suggested_by: z.string().optional(),
});
export type TakeSelect = z.infer<typeof TakeSelectSchema>;

/**
 * One line of 运行记录. `message.code` → `generate:log.<code>`; `params.model` is a model key
 * and `params.cost_usd` a number, both formatted by the UI.
 */
export const GenerateLogEntrySchema = z.object({
  id: z.string(),
  at: Timestamp,
  shot_label: z.string(),
  message: MessageSchema,
  /** Something went wrong or the user stepped in (amber in the UI). */
  warn: z.boolean(),
});
export type GenerateLogEntry = z.infer<typeof GenerateLogEntrySchema>;
