/**
 * 节拍看板 (M2 plan step 8, Kelvin 2026-10-19): one column per episode, its beats as cards. Drag a
 * card to another episode or place (`PATCH /beats/{id}` with `episode_id` / `position`); click
 * it to edit the text and emotion; the pencil on a column edits the episode. The whole-series
 * emotion curve sits above. Read-only while 分集规划 runs or is locked.
 */
import { Pencil } from "lucide-react";
import { useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { usePatchBeat } from "@/api/hooks/series";
import type { Beat, Episode } from "@/api/schemas/episodes";
import { useImpactGuard } from "@/components/impactGuardContext";
import { Button } from "@/components/ui/button";
import { formatEmotion } from "@/lib/beats";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EmotionCurve } from "@/pages/script/EmotionCurve";
import { BeatDialog, EpisodeDialog } from "@/pages/script/PlanDialogs";

const MIME = "application/x-drama-beat";

/** Where a drop would put the dragged beat: among the target episode's other beats. */
interface DropAt {
  episodeId: string;
  position: number;
}

export function BeatBoard({
  seriesId,
  episodes,
  readOnly,
}: {
  seriesId: string;
  episodes: Episode[];
  /** 分集规划 is running or locked: no drags, no edits. */
  readOnly: boolean;
}) {
  const { t } = useTranslation("script");
  const { t: tc } = useTranslation();
  const move = usePatchBeat(seriesId);
  const guard = useImpactGuard();
  const [dragging, setDragging] = useState<Beat | null>(null);
  const [dropAt, setDropAt] = useState<DropAt | null>(null);
  const [editing, setEditing] = useState<Beat | null>(null);
  const [editingEpisode, setEditingEpisode] = useState<Episode | null>(null);

  const others = (e: Episode) => e.beats.filter((b) => b.id !== dragging?.id);

  /** Over a card: before it in its upper half, after it in the lower half. */
  const overBeat = (e: Episode, b: Beat, ev: DragEvent) => {
    if (!dragging) return;
    ev.preventDefault();
    ev.stopPropagation(); // the column's own handler would put it last
    ev.dataTransfer.dropEffect = "move";
    const rect = ev.currentTarget.getBoundingClientRect();
    const after = rect.height > 0 && ev.clientY > rect.top + rect.height / 2;
    const i = others(e).findIndex((o) => o.id === b.id);
    const position = i < 0 ? others(e).length : i + (after ? 1 : 0);
    if (dropAt?.episodeId !== e.id || dropAt.position !== position)
      setDropAt({ episodeId: e.id, position });
  };

  const overEnd = (e: Episode, ev: DragEvent) => {
    if (!dragging) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    const position = others(e).length;
    if (dropAt?.episodeId !== e.id || dropAt.position !== position)
      setDropAt({ episodeId: e.id, position });
  };

  const drop = (ev: DragEvent) => {
    ev.preventDefault();
    ev.stopPropagation(); // a card's drop would reach its column too
    const beat = dragging;
    const at = dropAt;
    setDragging(null);
    setDropAt(null);
    if (!beat || !at) return;
    const source = episodes.find((e) => e.id === beat.episode_id);
    const same = at.episodeId === beat.episode_id && at.position === beat.idx - 1;
    if (!source || same) return;
    const target = episodes.find((e) => e.id === at.episodeId);
    const body = {
      position: at.position,
      ...(at.episodeId !== beat.episode_id ? { episode_id: at.episodeId } : {}),
    };
    // A confirmed script of either episode changes with it: preview first.
    if (guard && [source, target].some((e) => e?.script_status === "confirmed"))
      return guard({
        change: { kind: "beat_move", target_id: beat.id, patch: body },
        title: t("board.impactTitle"),
        detail: beat.text,
      });
    move.mutate(
      { id: beat.id, ...body },
      {
        onSuccess: () =>
          toast.success(t("board.moved", { n: target?.idx ?? 0, idx: at.position + 1 })),
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );
  };

  const end = () => {
    setDragging(null);
    setDropAt(null);
  };

  return (
    <div className="flex flex-col gap-3">
      <EmotionCurve episodes={episodes} />
      <div
        role="list"
        aria-label={t("episodes.view.board")}
        className="grid auto-cols-[minmax(15rem,1fr)] grid-flow-col gap-2.5 overflow-x-auto pb-1"
      >
        {episodes.map((e) => {
          const name = t("episodes.name", { n: e.idx, title: e.title });
          const meta = [
            t("board.meta", { count: e.beats.length, clock: formatClock(e.target_seconds ?? 0) }),
            e.scene_from !== null && e.scene_to !== null
              ? t("episodes.scenes", { from: e.scene_from, to: e.scene_to })
              : null,
          ].filter(Boolean);
          // The dragged card stays where it was (Chrome ends a drag whose source leaves the
          // page); a line over the cards (it moves nothing under the pointer) shows where it
          // would go among the others.
          const here = dropAt?.episodeId === e.id ? dropAt.position : null;
          const rest = others(e);
          const markBefore = here !== null ? (rest[here]?.id ?? null) : null;
          const markAfter = here !== null && here >= rest.length ? (rest.at(-1)?.id ?? null) : null;
          return (
            <section
              key={e.id}
              role="listitem"
              aria-label={name}
              data-episode={e.id}
              onDragOver={(ev) => overEnd(e, ev)}
              onDrop={drop}
              className={cn(
                "flex min-w-0 flex-col gap-2 rounded-lg border bg-muted/40 px-3 py-3",
                here !== null && "border-ring bg-accent/30",
              )}
            >
              <div className="flex items-start gap-1.5">
                <div className="mr-auto flex min-w-0 flex-col gap-0.5">
                  <h3 className="text-sm font-semibold">{name}</h3>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {meta.join(" · ")}
                  </span>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7"
                  aria-label={t("board.editEpisode", { n: e.idx })}
                  disabled={readOnly}
                  onClick={() => setEditingEpisode(e)}
                >
                  <Pencil className="size-3.5" aria-hidden />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                {e.hook ? t("board.hook", { text: e.hook }) : t("board.hookTbd")}
              </p>
              <ol className="flex flex-col gap-1.5">
                {e.beats.map((b) => (
                  <BeatCard
                    key={b.id}
                    beat={b}
                    episodeIdx={e.idx}
                    mark={markBefore === b.id ? "before" : markAfter === b.id ? "after" : null}
                    readOnly={readOnly}
                    dragging={dragging?.id === b.id}
                    onDragStart={(ev) => {
                      ev.dataTransfer.setData(MIME, b.id);
                      ev.dataTransfer.effectAllowed = "move";
                      setDragging(b);
                    }}
                    onDragOver={(ev) => overBeat(e, b, ev)}
                    onDrop={drop}
                    onDragEnd={end}
                    onEdit={() => setEditing(b)}
                  />
                ))}
              </ol>
              {dragging || e.beats.length === 0 ? (
                <div
                  data-drop-end
                  onDragOver={(ev) => {
                    ev.stopPropagation();
                    overEnd(e, ev);
                  }}
                  onDrop={drop}
                  className="rounded-md border border-dashed px-2 py-3 text-center text-xs text-muted-foreground"
                >
                  {e.beats.length === 0 && !dragging ? t("board.emptyColumn") : t("board.dropEnd")}
                </div>
              ) : null}
              <p className="mt-auto text-sm">
                {e.cliffhanger
                  ? t("episodes.cliffhanger", { text: e.cliffhanger })
                  : t("episodes.cliffhangerTbd")}
              </p>
            </section>
          );
        })}
      </div>
      <BeatDialog
        seriesId={seriesId}
        episodes={episodes}
        beat={editing}
        onClose={() => setEditing(null)}
      />
      <EpisodeDialog episode={editingEpisode} onClose={() => setEditingEpisode(null)} />
    </div>
  );
}

function BeatCard({
  beat,
  episodeIdx,
  mark,
  readOnly,
  dragging,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  onEdit,
}: {
  beat: Beat;
  episodeIdx: number;
  /** The drop line, when a drop would land just before or after this card. */
  mark: "before" | "after" | null;
  readOnly: boolean;
  dragging: boolean;
  onDragStart: (ev: DragEvent) => void;
  onDragOver: (ev: DragEvent) => void;
  onDrop: (ev: DragEvent) => void;
  onDragEnd: () => void;
  onEdit: () => void;
}) {
  const { t } = useTranslation("script");
  const v = beat.emotion;
  return (
    <li
      data-beat={beat.id}
      draggable={!readOnly}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      className={cn("relative", dragging && "opacity-40")}
    >
      {mark ? (
        <span
          aria-hidden
          data-drop-marker
          className={cn(
            "pointer-events-none absolute inset-x-0 h-0.5 rounded-full bg-primary",
            mark === "before" ? "-top-1" : "-bottom-1",
          )}
        />
      ) : null}
      <button
        type="button"
        disabled={readOnly}
        onClick={onEdit}
        aria-label={t("board.editBeat", { n: episodeIdx, idx: beat.idx, text: beat.text })}
        className={cn(
          "flex w-full flex-col gap-1.5 rounded-md border bg-card px-2.5 py-2 text-left text-sm outline-none hover:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:hover:border-border",
          !readOnly && "cursor-grab active:cursor-grabbing",
        )}
      >
        <span className="flex gap-1.5">
          <span className="w-4 shrink-0 text-xs text-muted-foreground tabular-nums">
            {beat.idx}
          </span>
          <span>{beat.text}</span>
        </span>
        <span className="flex items-center gap-1.5 pl-5.5 text-xs text-muted-foreground">
          <span aria-hidden className="relative h-1.5 w-12 rounded-full bg-muted">
            <span className="absolute inset-y-0 left-1/2 w-px bg-chart-grid" />
            <span
              data-emotion-bar
              className="absolute inset-y-0 rounded-full bg-chart-1"
              style={{
                left: `${50 - Math.max(0, -v) * 50}%`,
                width: `${Math.abs(v) * 50}%`,
              }}
            />
          </span>
          <span className="tabular-nums">{t("board.emotion", { value: formatEmotion(v) })}</span>
        </span>
      </button>
    </li>
  );
}
