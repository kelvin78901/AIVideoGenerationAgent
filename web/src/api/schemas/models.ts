/** Models a component can run on, as pickers and the 「不满意换一个」 menu list them (SPEC 7). */
import { z } from "zod";

import { PriceSchema, WhereSchema } from "@/api/schemas/common";

export const ModelOptionSchema = z.object({
  /** providers.yaml key, e.g. `deepseek/v4-pro`, `local/qwen3.6-27b`. */
  key: z.string(),
  /** Product name as the provider spells it; not translated. */
  display: z.string(),
  where: WhereSchema,
  /** List price; null for local models and custom endpoints without a price. */
  price: PriceSchema.nullable(),
});
export type ModelOption = z.infer<typeof ModelOptionSchema>;
