/** Dashboard metrics (SPEC 11.1). `/metrics/summary` also feeds the top bar's spend / budget. */
import { z } from "zod";

import { MessageSchema } from "@/api/schemas/common";

export const MetricsScopeSchema = z.enum(["episode", "series"]);
export type MetricsScope = z.infer<typeof MetricsScopeSchema>;

export const MetricsSummarySchema = z.object({
  scope: MetricsScopeSchema,
  /** Σ billed `model_call.cost_usd`. */
  spent_usd: z.number(),
  budget_usd: z.number().nullable(),
  /** Spent + remaining products × current-route estimate. */
  projected_usd: z.number(),
  /** 「值得注意」: sentences the UI renders from `dashboard.insight.<code>`. */
  insights: z.array(MessageSchema),
  updated_at: z.string(),
});
export type MetricsSummary = z.infer<typeof MetricsSummarySchema>;
