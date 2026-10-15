/**
 * Change impact (SPEC 9.1 `/impact/*`, PLAN 失效传播): what a change to confirmed upstream work
 * invalidates downstream, and what redoing it would cost.
 */
import { z } from "zod";

import { MessageSchema } from "@/api/schemas/common";
import { StepIdSchema } from "@/api/schemas/episodes";

export const ImpactChangeSchema = z.object({
  /** `line_edit`, `spec_aspect`, `asset_unlock` … */
  kind: z.string(),
  target_id: z.string(),
  patch: z.record(z.string(), z.unknown()).default({}),
});
export type ImpactChange = z.infer<typeof ImpactChangeSchema>;

/** One affected group, rendered from `components:impact.line.<code>`. */
export const ImpactLineSchema = MessageSchema.extend({
  /** Redo cost on the current route; null = free (local) or nothing to redo. */
  cost_usd: z.number().nullable(),
  /** Suggested, not required (e.g. reference images made for the old aspect). */
  optional: z.boolean(),
});
export type ImpactLine = z.infer<typeof ImpactLineSchema>;

export const ImpactSchema = z.object({
  id: z.string(),
  change: ImpactChangeSchema,
  lines: z.array(ImpactLineSchema),
  /** What stays valid, e.g. 「剧本、分镜表、配音和音色不受影响」. */
  unaffected: MessageSchema.nullable(),
  rerun_cost_usd: z.number(),
  /** Products each step would mark 待更新. */
  stale: z.partialRecord(StepIdSchema, z.number().int()),
});
export type Impact = z.infer<typeof ImpactSchema>;

export const ImpactActionSchema = z.enum(["mark", "rerun", "undo"]);
export type ImpactAction = z.infer<typeof ImpactActionSchema>;

export const ApplyImpactRequestSchema = z.object({
  impact_id: z.string(),
  action: ImpactActionSchema,
});

export const ApplyImpactResultSchema = z.object({
  action: ImpactActionSchema,
  stale: z.partialRecord(StepIdSchema, z.number().int()),
  job_ids: z.array(z.string()),
});
export type ApplyImpactResult = z.infer<typeof ApplyImpactResultSchema>;
