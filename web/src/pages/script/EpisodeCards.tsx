import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { Episode } from "@/api/schemas/episodes";
import { paths } from "@/app/paths";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 分集: one card per episode; picking one opens that episode's script. */
export function EpisodeCards({
  episodes,
  seriesId,
  currentIdx,
}: {
  episodes: Episode[];
  seriesId: string;
  currentIdx: number;
}) {
  const { t } = useTranslation("script");
  return (
    <section aria-labelledby="script-episodes" className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="script-episodes" className="text-base font-bold">
          {t("episodes.title")}
        </h2>
        <span className="text-xs text-muted-foreground">{t("episodes.lead")}</span>
      </div>
      <div className="grid gap-2.5 md:grid-cols-3">
        {episodes.map((e) => {
          const on = e.idx === currentIdx;
          const meta = [
            e.scene_from !== null && e.scene_to !== null
              ? t("episodes.scenes", { from: e.scene_from, to: e.scene_to })
              : null,
            e.shot_count !== null ? t("episodes.shots", { count: e.shot_count }) : null,
            e.target_seconds !== null
              ? t("episodes.length", { clock: formatClock(e.target_seconds) })
              : null,
          ].filter(Boolean);
          return (
            <Link
              key={e.id}
              to={paths.step(seriesId, String(e.idx), "script")}
              aria-current={on ? "page" : undefined}
              className={cn(
                "flex flex-col gap-1 rounded-lg border bg-card px-3.5 py-3 text-left outline-none hover:border-ring focus-visible:ring-2 focus-visible:ring-ring",
                on ? "border-primary" : "bg-muted/40",
              )}
            >
              <span className="text-sm font-semibold">
                {t("episodes.name", { n: e.idx, title: e.title })}
              </span>
              <span className="text-xs text-muted-foreground">{meta.join(" · ")}</span>
              <span className="text-sm">
                {e.cliffhanger
                  ? t("episodes.cliffhanger", { text: e.cliffhanger })
                  : t("episodes.cliffhangerTbd")}
              </span>
              <span
                className={cn(
                  "text-xs font-medium",
                  e.script_status === "confirmed" ? "text-tone-info-fg" : "text-muted-foreground",
                )}
              >
                {t(`episodes.status.${e.script_status}`)}
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
