/** Building blocks shared by the API schemas (SPEC 9.1). Field names are snake_case, as on the wire. */
import { z } from "zod";

/** Error body inside `detail` (`api/errors.py`); the front end translates `error.<code>`. */
export const ApiErrorBodySchema = z.object({
  code: z.string(),
  params: z.record(z.string(), z.unknown()).default({}),
});
export type ApiErrorBody = z.infer<typeof ApiErrorBodySchema>;

/** ISO 8601 timestamp with offset, as produced by `datetime.isoformat()`. */
export const Timestamp = z.string();

/** `local` runs on this machine (no API fee); `api` calls a provider. */
export const WhereSchema = z.enum(["local", "api"]);
export type Where = z.infer<typeof WhereSchema>;

/** A sentence the UI renders from the dictionaries: `t(code, params)`. */
export const MessageSchema = z.object({
  code: z.string(),
  params: z.record(z.string(), z.union([z.string(), z.number()])).default({}),
});
export type Message = z.infer<typeof MessageSchema>;

/**
 * A model's list price (providers.yaml). LLMs are priced per million tokens in / out; media
 * models per image, per second of video or per call. CNY prices are shown as ¥.
 */
export const CurrencySchema = z.enum(["USD", "CNY"]);
export type Currency = z.infer<typeof CurrencySchema>;

export const PriceSchema = z.union([
  z.object({ unit: z.literal("mtok"), in: z.number(), out: z.number(), currency: CurrencySchema }),
  z.object({
    unit: z.enum(["image", "second", "call"]),
    amount: z.number(),
    currency: CurrencySchema,
  }),
]);
export type Price = z.infer<typeof PriceSchema>;
