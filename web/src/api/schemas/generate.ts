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
