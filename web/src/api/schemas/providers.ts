/**
 * `GET /providers`: writing-model providers, their sites (China / international), whether a key
 * is set, the model list the provider answered and which of it is picked (M5 step 7a).
 */
import { z } from "zod";

import { WhereSchema } from "@/api/schemas/common";

/** Per million tokens, in the currency the provider bills in. */
export const TokenPriceSchema = z.object({ in: z.number(), out: z.number(), currency: z.string() });
export type TokenPrice = z.infer<typeof TokenPriceSchema>;

export const ProviderSiteSchema = z.object({
  /** `cn` / `intl`; `main` for a provider with one address. */
  id: z.string(),
  base_url: z.string().nullable(),
  docs: z.string().nullable(),
  has_key: z.boolean(),
});
export type ProviderSite = z.infer<typeof ProviderSiteSchema>;

/** One id of the provider's own list: picked or not, and its price (the user's, the reference
 * table's, or unknown). */
export const ListedModelSchema = z.object({
  model_id: z.string(),
  key: z.string(),
  display: z.string(),
  in_table: z.boolean(),
  enabled: z.boolean(),
  price: TokenPriceSchema.nullable(),
  price_source: z.enum(["user", "table"]).nullable(),
});
export type ListedModel = z.infer<typeof ListedModelSchema>;

export const ProviderSchema = z.object({
  id: z.string(),
  name: z.string(),
  where: WhereSchema,
  /** The site the provider is called on now (its key, address and prices). */
  site: z.string().default("main"),
  sites: z.array(ProviderSiteSchema).default([]),
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
      price: TokenPriceSchema.nullable(),
      json_mode: z.boolean(),
    }),
  ),
  /** The list from the last 「测试连接」 on this site; null = never fetched (the reference table
   * stands). */
  listed: z
    .object({
      site: z.string().nullable(),
      fetched_at: z.string().nullable(),
      models: z.array(ListedModelSchema),
    })
    .nullable()
    .default(null),
  /** Media models that use this provider's key (pictures, voices, video). */
  media: z
    .array(
      z.object({
        key: z.string(),
        display: z.string(),
        model_id: z.string().nullable().default(null),
        /** The model id is the user's, not the config's. */
        custom_model_id: z.boolean().default(false),
      }),
    )
    .default([]),
});
export type Provider = z.infer<typeof ProviderSchema>;

export const ProvidersSchema = z.object({
  providers: z.array(ProviderSchema),
  llm_ui_order: z.array(z.string()),
});
export type Providers = z.infer<typeof ProvidersSchema>;

/** `PUT /providers/settings/{model_key}`: a writing model's price, a media model's id. */
export const ModelSettingSchema = z.object({
  model_key: z.string(),
  model_id: z.string().nullable(),
  price: TokenPriceSchema.nullable(),
});
