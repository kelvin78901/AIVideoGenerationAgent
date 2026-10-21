/**
 * 分集: the adopted plan as cards (pick one to open its script) or as the beat board with the
 * emotion curve (M2 plan step 8). Before any plan, an empty state that runs 分集规划.
 */
import { useTranslation } from "react-i18next";

import type { Episode } from "@/api/schemas/episodes";
import type { Product } from "@/api/schemas/products";
import { EmptyState } from "@/components/EmptyState";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/ui/button";
import { BeatBoard } from "@/pages/script/BeatBoard";
import { EpisodeCards } from "@/pages/script/EpisodeCards";

export type EpisodeView = "cards" | "board";

export function Episodes({
  seriesId,
  episodes,
  currentIdx,
  split,
  view,
  onViewChange,
  onRunSplit,
  onOpenHistory,
}: {
  seriesId: string;
  episodes: Episode[];
  currentIdx: number;
  /** The series' 分集规划 product (absent before the novel is imported). */
  split: Product | undefined;
  view: EpisodeView;
  onViewChange: (view: EpisodeView) => void;
  onRunSplit: () => void;
  onOpenHistory: () => void;
}) {
  const { t } = useTranslation("script");
  const busy = !!split?.running;
  const locked = split?.status === "locked";
  const unadopted =
    !!split?.adopted_version_id && split.current_version_id !== split.adopted_version_id;

  return (
    <section aria-labelledby="script-episodes" className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 id="script-episodes" className="text-base font-bold">
          {t("episodes.title")}
        </h2>
        <span className="text-xs text-muted-foreground">
          {view === "board" ? t("board.lead") : t("episodes.lead")}
        </span>
        {episodes.length ? (
          <SegmentedControl
            className="ml-auto"
            size="sm"
            label={t("episodes.views")}
            value={view}
            onChange={onViewChange}
            options={(["cards", "board"] as const).map((v) => ({
              value: v,
              label: t(`episodes.view.${v}`),
            }))}
          />
        ) : null}
      </div>
      {episodes.length === 0 ? (
        <EmptyState
          title={t("episodes.empty.title")}
          description={t("episodes.empty.lead")}
          action={
            <Button disabled={!split || busy} onClick={onRunSplit}>
              {t("episodes.empty.run")}
            </Button>
          }
        />
      ) : view === "cards" ? (
        <EpisodeCards episodes={episodes} seriesId={seriesId} currentIdx={currentIdx} />
      ) : (
        <>
          {unadopted || busy || locked ? (
            <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
              {busy ? t("board.busy") : locked ? t("board.locked") : t("board.unadopted")}
              {unadopted && !busy ? (
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-xs"
                  onClick={onOpenHistory}
                >
                  {t("board.openHistory")}
                </Button>
              ) : null}
            </p>
          ) : null}
          <BeatBoard seriesId={seriesId} episodes={episodes} readOnly={busy || locked} />
        </>
      )}
    </section>
  );
}
