/** Series (SPEC 4.1, 9.1 `GET /series/{id}`). */
import { z } from "zod";

import { Timestamp } from "@/api/schemas/common";

export const SeriesSchema = z.object({
  id: z.string(),
  slug: z.string(),
  title: z.string(),
  ui_lang: z.enum(["zh-CN", "en"]),
  created_at: Timestamp,
});
export type Series = z.infer<typeof SeriesSchema>;
