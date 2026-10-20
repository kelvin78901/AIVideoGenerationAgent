/** Step gates (SPEC 4.2 `gate_decision`): 「确认……，进入下一步」 and reopening. */
import { z } from "zod";

import { Timestamp } from "@/api/schemas/common";
import type { StepId } from "@/api/schemas/episodes";

export const GateSchema = z.enum(["novel", "script", "assets", "storyboard", "takes", "export"]);
export type Gate = z.infer<typeof GateSchema>;

/** The production step each gate closes. */
export const GATE_STEP: Record<Gate, StepId> = {
  novel: "novel",
  script: "script",
  assets: "assets",
  storyboard: "storyboard",
  takes: "generate",
  export: "post",
};

export const GateDecisionSchema = z.object({
  id: z.string(),
  gate: GateSchema,
  /** The series (novel gate) or the episode. */
  scope_id: z.string(),
  action: z.enum(["confirm", "reopen"]),
  decided_at: Timestamp,
});
export type GateDecision = z.infer<typeof GateDecisionSchema>;
