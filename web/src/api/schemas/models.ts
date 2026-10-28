/** Models a component can run on, as pickers and the 「不满意换一个」 menu list them (SPEC 7). */
import { z } from "zod";

import { PriceSchema, WhereSchema } from "@/api/schemas/common";
import { WorkflowTierSchema } from "@/api/schemas/workflows";

export const ModelOptionSchema = z.object({
  /** providers.yaml key, e.g. `deepseek/v4-pro`, `local/qwen3.6-27b`. */
  key: z.string(),
  /** Product name as the provider spells it; not translated. */
  display: z.string(),
  where: WhereSchema,
  /** List price; null for local models and custom endpoints without a price. */
  price: PriceSchema.nullable(),
  /** False: an API model nobody priced yet; every run on it asks first (absent = priced). */
  priced: z.boolean().optional(),
  /** A ComfyUI workflow's library tier; unverified ones are picked by hand only (SPEC 6.4.4). */
  tier: WorkflowTierSchema.nullable().optional(),
});
export type ModelOption = z.infer<typeof ModelOptionSchema>;
