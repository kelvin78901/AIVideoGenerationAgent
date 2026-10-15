/** `GET /providers` (implemented in M0): writing-model providers and whether a key is set. */
import { z } from "zod";

import { WhereSchema } from "@/api/schemas/common";

export const ProviderSchema = z.object({
  id: z.string(),
  name: z.string(),
  where: WhereSchema,
  base_url: z.string().nullable(),
  docs: z.string().nullable(),
  verify: z.boolean(),
  needs_key: z.boolean(),
  has_key: z.boolean(),
  key_source: z.enum(["keyring", "env", "none"]),
  enabled: z.boolean(),
  models: z.array(
    z.object({
      key: z.string(),
      display: z.string(),
      model_id: z.string().nullable(),
      price: z.object({ in: z.number(), out: z.number(), currency: z.string() }).nullable(),
      json_mode: z.boolean(),
    }),
  ),
});
export type Provider = z.infer<typeof ProviderSchema>;

export const ProvidersSchema = z.object({
  providers: z.array(ProviderSchema),
  llm_ui_order: z.array(z.string()),
});
export type Providers = z.infer<typeof ProvidersSchema>;
