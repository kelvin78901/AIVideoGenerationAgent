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
