import type { TFunction } from "i18next";

import type { Novel, NovelChapter, Suggestion } from "@/api/schemas/novel";

/** Characters of the shown chapter as it will be used: the original plus adopted additions. */
export function charCount(novel: Novel, suggestions: Suggestion[]): number {
  const shown = new Set(novel.paragraphs.map((p) => p.idx));
  const base = novel.paragraphs.reduce((n, p) => n + [...p.text].length, 0);
  return suggestions
    .filter((s) => s.status === "accepted" && shown.has(s.para_idx))
    .reduce((n, s) => n + [...s.text].length, base);
}

/** The heading line; else 「正文前」 (text before the first heading) or 「第 N 部分」. */
export function chapterLabel(
  t: TFunction<"novel">,
  chapter: Pick<NovelChapter, "idx" | "title">,
  splitBy: "heading" | "length",
): string {
  if (chapter.title) return chapter.title;
  return splitBy === "length" ? t("chapter.part", { n: chapter.idx + 1 }) : t("chapter.untitled");
}

/** The chapter a paragraph (numbered across the book) is in. */
export function chapterOf(chapters: NovelChapter[], para: number): NovelChapter | undefined {
  return chapters.find((c) => para >= c.para_start && para < c.para_start + c.para_count);
}
