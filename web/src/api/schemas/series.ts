/** Series (SPEC 4.1, 9.1 `GET / POST /series`, `GET / PATCH /series/{id}`). */
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

/** `POST /series`: the title is trimmed; 1–80 characters. */
export const SeriesCreateSchema = z.object({
  title: z.string().trim().min(1).max(80),
  ui_lang: z.enum(["zh-CN", "en"]).optional(),
});
export type SeriesCreate = z.infer<typeof SeriesCreateSchema>;
