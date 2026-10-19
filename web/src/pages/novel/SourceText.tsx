import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useEditChapter } from "@/api/hooks/novel";
import type { Novel, Suggestion } from "@/api/schemas/novel";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/form";
import { cn } from "@/lib/utils";
import { chapterLabel, charCount } from "@/pages/novel/text";

export type NovelView = "orig" | "after" | "diff";

/** What is being edited: a paragraph (its place in the chapter), a new one after `at`, a
 * delete waiting for its yes, or the chapter title. */
type Draft =
  | { kind: "para"; at: number; text: string }
  | { kind: "insert"; at: number; text: string }
  | { kind: "delete"; at: number }
  | { kind: "title"; text: string };

/**
 * 原文 of one chapter with the adopted additions: hidden (原文), inline (采纳后) or highlighted
 * (对比). Paragraphs are numbered across the book; a novel with several chapters gets a picker.
 * The paragraphs of the bible entry picked below are marked.
 *
 * In 原文 (only there: the other views show additions that are not the author's text) each
 * paragraph can be edited, deleted or followed by a new one, and the chapter retitled; saving
 * sends the whole chapter and makes a new novel version (M2 step 7b).
 */
export function SourceText({
  seriesId,
  novel,
  suggestions,
  view,
  onViewChange,
  onChapterChange,
  focus,
  marked = [],
  editable = false,
  downstream = false,
}: {
  seriesId: string;
  novel: Novel;
  suggestions: Suggestion[];
  view: NovelView;
  onViewChange: (v: NovelView) => void;
  onChapterChange: (idx: number) => void;
  /** Paragraph highlighted from a suggestion's 「第 N 段」. */
  focus: number | null;
  /** Paragraphs that mention the bible entry picked in 提取到的设定. */
  marked?: number[];
  /** The novel can be edited (it is not locked by its gate). */
  editable?: boolean;
  /** Something adopted was built from the novel (an edit turns it 待更新). */
  downstream?: boolean;
}) {
  const { t } = useTranslation("novel");
  const { t: tc } = useTranslation();
  const edit = useEditChapter(seriesId);
  const [draft, setDraft] = useState<Draft | null>(null);
  const accepted = suggestions.filter((s) => s.status === "accepted");
  const splitBy = novel.source?.split_by ?? "heading";
  const chapter = novel.chapters.find((c) => c.idx === novel.chapter);
  const canEdit = editable && view === "orig" && chapter !== undefined;

  const save = (paragraphs: string[], title = chapter?.title ?? null) => {
    if (!chapter) return;
    edit.mutate(
      { idx: chapter.idx, title, paragraphs },
      {
        onSuccess: () => {
          setDraft(null);
          toast.success(t("edit.saved"));
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );
  };
  const texts = novel.paragraphs.map((p) => p.text);
  const saveDraft = () => {
    if (!draft) return;
    if (draft.kind === "title") return save(texts, draft.text.trim() || null);
    const next = [...texts];
    if (draft.kind === "para") next[draft.at] = draft.text;
    else if (draft.kind === "insert") next.splice(draft.at + 1, 0, draft.text);
    else next.splice(draft.at, 1);
    save(next);
  };
  const editor = (label: string) =>
    draft && draft.kind !== "delete" ? (
      <div className="flex flex-1 flex-col gap-2">
        <Label htmlFor="novel-edit" className="sr-only">
          {label}
        </Label>
        {draft.kind === "title" ? (
          <Input
            id="novel-edit"
            autoFocus
            value={draft.text}
            onChange={(e) => setDraft({ ...draft, text: e.target.value })}
          />
        ) : (
          <Textarea
            id="novel-edit"
            autoFocus
            rows={4}
            value={draft.text}
            onChange={(e) => setDraft({ ...draft, text: e.target.value })}
            className="text-[15px] leading-7"
          />
        )}
        {downstream ? (
          <p className="text-xs text-muted-foreground">{t("edit.downstream")}</p>
        ) : null}
        <div className="flex gap-2 self-end">
          <Button variant="outline" size="sm" onClick={() => setDraft(null)}>
            {t("edit.cancel")}
          </Button>
          <Button
            size="sm"
            disabled={edit.isPending || (draft.kind !== "title" && !draft.text.trim())}
            onClick={saveDraft}
          >
            {t("edit.save")}
          </Button>
        </div>
      </div>
    ) : null;

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
          onChange={(v) => {
            setDraft(null);
            onViewChange(v);
          }}
          options={(["orig", "after", "diff"] as const).map((v) => ({
            value: v,
            label: t(`source.view.${v}`),
          }))}
        />
      </div>
      {novel.chapters.length > 1 || canEdit ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {novel.chapters.length > 1 ? (
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">{t("chapter.label")}</span>
              <select
                value={novel.chapter ?? 0}
                onChange={(e) => {
                  setDraft(null);
                  onChapterChange(Number(e.target.value));
                }}
                className="h-8 max-w-72 rounded-md border border-input bg-card px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
              >
                {novel.chapters.map((c) => (
                  <option key={c.idx} value={c.idx}>
                    {t("chapter.option", { title: chapterLabel(t, c, splitBy), chars: c.chars })}
                  </option>
                ))}
              </select>
            </label>
          ) : chapter ? (
            <span className="text-sm font-medium">{chapterLabel(t, chapter, splitBy)}</span>
          ) : null}
          {canEdit && draft?.kind !== "title" ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDraft({ kind: "title", text: chapter?.title ?? "" })}
            >
              <Pencil aria-hidden />
              {t("edit.title")}
            </Button>
          ) : null}
          {novel.source && novel.chapters.length > 1 ? (
            <span className="text-xs text-muted-foreground tabular-nums">
              {t("chapter.book", { chapters: novel.chapters.length, chars: novel.source.chars })}
            </span>
          ) : null}
        </div>
      ) : null}
      {draft?.kind === "title" ? editor(t("edit.titleLabel")) : null}
      {view === "diff" ? (
        <p className="text-xs text-muted-foreground">{t("source.diffHint")}</p>
      ) : null}
      {editable && view !== "orig" ? (
        <p className="text-xs text-muted-foreground">{t("edit.switchHint")}</p>
      ) : null}
      <ol className="flex flex-col gap-1">
        {novel.paragraphs.map((p, at) => {
          const adds = view === "orig" ? [] : accepted.filter((s) => s.para_idx === p.idx);
          const n = p.idx + 1;
          const editing = canEdit && draft?.kind === "para" && draft.at === at;
          return (
            <li key={p.idx} className="flex flex-col gap-1">
              <div
                id={`novel-para-${p.idx}`}
                data-focused={focus === p.idx || undefined}
                data-marked={marked.includes(p.idx) || undefined}
                className={cn(
                  "group relative flex gap-3 rounded-md border border-transparent px-2.5 py-2 transition-colors",
                  marked.includes(p.idx) && "border-tone-warn-border bg-tone-warn-bg/50",
                  focus === p.idx && "border-tone-info-border bg-tone-info-bg/50",
                )}
              >
                <span className="w-5 shrink-0 pt-1 font-mono text-xs text-muted-foreground">
                  {String(n).padStart(2, "0")}
                </span>
                {editing ? (
                  editor(t("edit.label", { n }))
                ) : (
                  <p className="flex-1 text-[15px] leading-8">
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
                )}
                {canEdit && !editing ? (
                  <div className="absolute top-1 right-1 flex gap-0.5 rounded-md border bg-card text-muted-foreground opacity-0 shadow-sm transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 [&_button]:size-7">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("edit.para", { n })}
                      onClick={() => setDraft({ kind: "para", at, text: p.text })}
                    >
                      <Pencil aria-hidden />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("edit.insert", { n })}
                      onClick={() => setDraft({ kind: "insert", at, text: "" })}
                    >
                      <Plus aria-hidden />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("edit.delete", { n })}
                      onClick={() => setDraft({ kind: "delete", at })}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  </div>
                ) : null}
              </div>
              {canEdit && draft?.kind === "delete" && draft.at === at ? (
                <div
                  role="alert"
                  className="ml-8 flex flex-wrap items-center gap-2 rounded-md bg-tone-warn-bg px-3 py-2 text-sm text-tone-warn-fg"
                >
                  <span>{t("edit.deleteConfirm", { n })}</span>
                  {downstream ? <span className="text-xs">{t("edit.downstream")}</span> : null}
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto"
                    onClick={() => setDraft(null)}
                  >
                    {t("edit.cancel")}
                  </Button>
                  <Button size="sm" disabled={edit.isPending} onClick={saveDraft}>
                    {t("edit.deleteYes")}
                  </Button>
                </div>
              ) : null}
              {canEdit && draft?.kind === "insert" && draft.at === at ? (
                <div className="ml-8 flex">{editor(t("edit.newLabel", { n }))}</div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
