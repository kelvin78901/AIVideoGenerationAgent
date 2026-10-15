import { useTranslation } from "react-i18next";

import type { Novel, Suggestion } from "@/api/schemas/novel";
import { SegmentedControl } from "@/components/SegmentedControl";
import { cn } from "@/lib/utils";
import { charCount } from "@/pages/novel/text";

export type NovelView = "orig" | "after" | "diff";

/** 原文 with the adopted additions: hidden (原文), inline (采纳后) or highlighted (对比). */
export function SourceText({
  novel,
  suggestions,
  view,
  onViewChange,
  focus,
}: {
  novel: Novel;
  suggestions: Suggestion[];
  view: NovelView;
  onViewChange: (v: NovelView) => void;
  /** Paragraph highlighted from a suggestion's 「第 N 段」. */
  focus: number | null;
}) {
  const { t } = useTranslation("novel");
  const accepted = suggestions.filter((s) => s.status === "accepted");
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
              className={cn(
                "flex gap-3 rounded-md border border-transparent px-2.5 py-2 transition-colors",
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
