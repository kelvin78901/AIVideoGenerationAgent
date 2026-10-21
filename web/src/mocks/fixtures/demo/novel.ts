/**
 * 《雨停之前》 chapter 1 as the backend answers it (`test/data/novel.json`): the demo script's
 * source spans point into its text. The novel, its suggestions (小说补全) and its bible come from
 * the backend (seeded in Mock mode from `tests/fixtures/demo/`).
 */
import { NovelSchema } from "@/api/schemas/novel";
import data from "@/test/data/novel.json";

export const SOURCE = "demo-src";

/** `GET /series/demo/novel` (chapter 1 《红伞》: paragraphs 01–05). */
export const novel = NovelSchema.parse(data.chapters[0]);
