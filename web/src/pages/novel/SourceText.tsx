import { useTranslation } from "react-i18next";

import type { Novel, Suggestion } from "@/api/schemas/novel";
import { SegmentedControl } from "@/components/SegmentedControl";
import { cn } from "@/lib/utils";
import { chapterLabel, charCount } from "@/pages/novel/text";

export type NovelView = "orig" | "after" | "diff";

/**
 * 原文 of one chapter with the adopted additions: hidden (原文), inline (采纳后) or highlighted
 * (对比). Paragraphs are numbered across the book; a novel with several chapters gets a picker.
 * The paragraphs of the bible entry picked below are marked.
 */
export function SourceText({
  novel,
  suggestions,
  view,
  onViewChange,
  onChapterChange,
  focus,
  marked = [],
}: {
  novel: Novel;
  suggestions: Suggestion[];
  view: NovelView;
  onViewChange: (v: NovelView) => void;
  onChapterChange: (idx: number) => void;
  /** Paragraph highlighted from a suggestion's 「第 N 段」. */
  focus: number | null;
  /** Paragraphs that mention the bible entry picked in 提取到的设定. */
  marked?: number[];
}) {
  const { t } = useTranslation("novel");
  const accepted = suggestions.filter((s) => s.status === "accepted");
  const splitBy = novel.source?.split_by ?? "heading";
  return (
    <section
      aria-labelledby="novel-source"
      className="flex flex-col gap-3 rounded-lg border bg-card p-4"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 id="novel-source" className="text-base font-bold">
          {t("source.title")}
        </h2>
        <span className="text-xs text-muted-foreground tabular-nums">
          {t("source.meta", {
            chars: charCount(novel, suggestions),
            paras: novel.paragraphs.length,
          })}
        </span>
        <SegmentedControl
          className="ml-auto"
          size="sm"
          label={t("source.views")}
          value={view}
          onChange={onViewChange}
          options={(["orig", "after", "diff"] as const).map((v) => ({
            value: v,
            label: t(`source.view.${v}`),
          }))}
        />
      </div>
      {novel.chapters.length > 1 ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t("chapter.label")}</span>
            <select
              value={novel.chapter ?? 0}
              onChange={(e) => onChapterChange(Number(e.target.value))}
              className="h-8 max-w-72 rounded-md border border-input bg-card px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              {novel.chapters.map((c) => (
                <option key={c.idx} value={c.idx}>
                  {t("chapter.option", { title: chapterLabel(t, c, splitBy), chars: c.chars })}
                </option>
              ))}
            </select>
          </label>
          {novel.source ? (
            <span className="text-xs text-muted-foreground tabular-nums">
              {t("chapter.book", { chapters: novel.chapters.length, chars: novel.source.chars })}
            </span>
          ) : null}
        </div>
      ) : null}
      {view === "diff" ? (
        <p className="text-xs text-muted-foreground">{t("source.diffHint")}</p>
      ) : null}
      <ol className="flex flex-col gap-1">
        {novel.paragraphs.map((p) => {
          const adds = view === "orig" ? [] : accepted.filter((s) => s.para_idx === p.idx);
          return (
            <li
              key={p.idx}
              id={`novel-para-${p.idx}`}
              data-focused={focus === p.idx || undefined}
              data-marked={marked.includes(p.idx) || undefined}
              className={cn(
                "flex gap-3 rounded-md border border-transparent px-2.5 py-2 transition-colors",
                marked.includes(p.idx) && "border-tone-warn-border bg-tone-warn-bg/50",
                focus === p.idx && "border-tone-info-border bg-tone-info-bg/50",
              )}
            >
              <span className="w-5 shrink-0 pt-1 font-mono text-xs text-muted-foreground">
                {String(p.idx + 1).padStart(2, "0")}
              </span>
              <p className="text-[15px] leading-8">
                {p.text}
                {adds.map((s) =>
                  view === "diff" ? (
                    <mark
                      key={s.id}
                      className="rounded-sm bg-tone-info-bg px-0.5 text-tone-info-fg"
                    >
                      <span className="sr-only">{t("source.added")}</span>
                      <span aria-hidden>{t("source.addedMark")}</span>
                      {s.text}
                    </mark>
                  ) : (
                    <span key={s.id}>{s.text}</span>
                  ),
                )}
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
