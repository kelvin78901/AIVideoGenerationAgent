import { Lock, Pencil } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useMergeBible } from "@/api/hooks/novel";
import type { Bible, BibleEntity, MergeSuggestion } from "@/api/schemas/novel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { EntityDialog } from "@/pages/novel/EntityDialog";

const COLUMNS = ["character", "location", "prop", "event"] as const;

/**
 * 提取到的设定: the extract component's output in four columns (prototype Main.dc.html). An
 * entry marks its paragraphs in the text (the page moves there); the pencil edits it and
 * 「可能是同一个」 asks about entries the model thinks are one.
 */
export function BiblePanel({
  seriesId,
  bible,
  assetsPath,
  selected,
  onSelect,
}: {
  seriesId: string;
  bible: Bible;
  assetsPath: string;
  /** The entry marked in the text. */
  selected: string | null;
  onSelect: (entity: BibleEntity | null) => void;
}) {
  const { t } = useTranslation("novel");
  const [editing, setEditing] = useState<BibleEntity | null>(null);
  const shown = bible.entities.find((e) => e.id === selected);
  return (
    <section
      aria-labelledby="novel-bible"
      className="flex flex-col gap-3 rounded-lg border bg-card p-4"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="novel-bible" className="text-base font-bold">
          {t("bible.title")}
        </h2>
        {bible.adopted ? null : <Badge variant="warn">{t("bible.unadopted")}</Badge>}
        <span className="text-xs text-muted-foreground">{t("bible.lead")}</span>
        <Link
          to={assetsPath}
          className="ml-auto text-sm text-primary underline-offset-4 hover:underline"
        >
          {t("bible.link")}
        </Link>
      </div>
      {bible.adopted ? null : (
        <p className="text-xs text-muted-foreground">{t("bible.unadoptedHint")}</p>
      )}

      {bible.merge_suggestions.length > 0 ? (
        <SameSuggestions seriesId={seriesId} bible={bible} />
      ) : null}

      {bible.entities.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("bible.none")}</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {COLUMNS.map((kind) => {
            const items = bible.entities.filter((e) => e.kind === kind);
            return (
              <div key={kind} className="flex min-w-0 flex-col gap-1.5">
                <h3 className="text-xs text-muted-foreground">{t(`bible.kind.${kind}`)}</h3>
                <ul aria-label={t(`bible.kind.${kind}`)} className="flex flex-col gap-0.5 text-sm">
                  {items.map((e) => (
                    <li key={e.id} className="group flex items-start gap-0.5">
                      <button
                        type="button"
                        aria-pressed={selected === e.id}
                        title={t("bible.show", { name: e.name })}
                        onClick={() => onSelect(selected === e.id ? null : e)}
                        className={cn(
                          "min-w-0 flex-1 rounded-md px-1.5 py-0.5 text-left leading-6 transition-colors hover:bg-muted",
                          "focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none",
                          selected === e.id &&
                            "bg-tone-info-bg text-tone-info-fg hover:bg-tone-info-bg",
                        )}
                      >
                        {e.name}
                        {e.data.summary ? ` · ${e.data.summary}` : ""}
                        {e.frozen ? (
                          <>
                            <Lock aria-hidden className="ml-1 inline size-3.5 align-[-2px]" />
                            <span className="sr-only">{t("bible.frozen")}</span>
                          </>
                        ) : null}
                      </button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 shrink-0 text-muted-foreground opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 focus-visible:opacity-100"
                        aria-label={t("bible.edit", { name: e.name })}
                        onClick={() => setEditing(e)}
                      >
                        <Pencil aria-hidden />
                      </Button>
                    </li>
                  ))}
                  {items.length === 0 ? (
                    <li className="px-1.5 text-muted-foreground">{t("bible.empty")}</li>
                  ) : null}
                </ul>
              </div>
            );
          })}
        </div>
      )}

      <p aria-live="polite" className="min-h-4 text-xs text-muted-foreground">
        {shown
          ? shown.paras.length > 0
            ? t("bible.shown", { name: shown.name, count: shown.paras.length })
            : t("bible.shownNone", { name: shown.name })
          : null}
      </p>

      <EntityDialog
        seriesId={seriesId}
        entity={editing}
        onOpenChange={(open) => (open ? null : setEditing(null))}
      />
    </section>
  );
}

/** The entry that stays when merging: the one the text mentions more. */
function keepFirst(entities: BibleEntity[], s: MergeSuggestion): BibleEntity[] {
  const pair = s.ids
    .map((id) => entities.find((e) => e.id === id))
    .filter((e): e is BibleEntity => e !== undefined);
  return [...pair].sort((a, b) => b.paras.length - a.paras.length);
}

/** 「可能是同一个」: merge (the first stays, the other becomes its alias) or keep apart. */
function SameSuggestions({ seriesId, bible }: { seriesId: string; bible: Bible }) {
  const { t } = useTranslation("novel");
  const { t: tc } = useTranslation();
  const merge = useMergeBible(seriesId);
  return (
    <div
      role="group"
      aria-labelledby="novel-bible-same"
      className="flex flex-col gap-2 rounded-md border border-tone-warn-border bg-tone-warn-bg/40 p-3"
    >
      <h3 id="novel-bible-same" className="text-sm font-semibold">
        {t("bible.same.title")}
      </h3>
      <ul className="flex flex-col gap-2">
        {bible.merge_suggestions.map((s) => {
          const [a, b] = keepFirst(bible.entities, s);
          if (!a || !b) return null;
          const names = { a: a.name, b: b.name };
          const send = (action: "merge" | "distinct") =>
            merge.mutate(
              { action, ids: [a.id, b.id] },
              {
                onSuccess: () =>
                  action === "merge" ? toast.success(t("bible.same.merged", names)) : undefined,
                onError: (err) => toast.error(errorMessage(tc, err)),
              },
            );
          return (
            <li key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
              <span className="font-medium">{t("bible.same.pair", names)}</span>
              {s.reason ? <span className="text-xs text-muted-foreground">{s.reason}</span> : null}
              <span className="ml-auto flex gap-2">
                <Button
                  size="sm"
                  aria-label={t("bible.same.mergeLabel", names)}
                  disabled={merge.isPending}
                  onClick={() => send("merge")}
                >
                  {t("bible.same.merge")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  aria-label={t("bible.same.distinctLabel", names)}
                  disabled={merge.isPending}
                  onClick={() => send("distinct")}
                >
                  {t("bible.same.distinct")}
                </Button>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
