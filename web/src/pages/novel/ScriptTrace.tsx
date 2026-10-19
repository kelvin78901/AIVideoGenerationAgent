import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useScript } from "@/api/hooks/script";
import type { Episode } from "@/api/schemas/episodes";
import { paths } from "@/app/paths";
import { Skeleton } from "@/components/QueryState";
import { Button } from "@/components/ui/button";
import { scriptBlocks, useBlockLead } from "@/pages/script/blocks";

/**
 * 段落 → 剧本行 (M2 step 9): where one paragraph of the novel went. The episode whose beats
 * cite it (分集规划), then the lines of that episode's script that come from it, each a link to
 * the script page with the line selected.
 */
export function ScriptTrace({
  seriesId,
  para,
  episodes,
  onClose,
}: {
  seriesId: string;
  /** 0-based, across the book. */
  para: number;
  episodes: Episode[];
  onClose: () => void;
}) {
  const { t } = useTranslation("novel");
  const leadOf = useBlockLead();
  const episode = episodes.find((e) => e.beats.some((b) => b.paras.includes(para)));
  const script = useScript(episode?.id);
  const scriptPath = (lineId?: string) =>
    episode
      ? paths.step(seriesId, String(episode.idx), "script") +
        (lineId ? `?line=${encodeURIComponent(lineId)}` : "")
      : "";
  const sceneOf = (id: string) => script.data?.scenes.find((s) => s.id === id)?.idx ?? 0;
  const lines = script.data
    ? scriptBlocks(script.data).filter((b) => b.kind !== "scene" && b.paras.includes(para))
    : [];

  let body;
  if (!episode) body = <p className="text-muted-foreground">{t("trace.notPlanned")}</p>;
  else if (!script.data) body = <Skeleton className="h-10 w-full" />;
  else if (script.data.scenes.length === 0)
    body = (
      <p className="text-muted-foreground">
        {t("trace.noScript", { ep: episode.idx })}{" "}
        <Link to={scriptPath()} className="text-primary underline-offset-4 hover:underline">
          {t("trace.open")}
        </Link>
      </p>
    );
  else if (lines.length === 0) body = <p className="text-muted-foreground">{t("trace.none")}</p>;
  else
    body = (
      <ul className="flex flex-col gap-1">
        {lines.map((b) => (
          <li key={b.id}>
            <Link
              to={scriptPath(b.id)}
              className="flex flex-wrap gap-x-2 rounded-sm underline-offset-4 hover:underline"
            >
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {t("trace.where", {
                  ep: episode.idx,
                  scene: b.kind === "scene" ? b.scene.idx : sceneOf(b.line.scene_id),
                })}
              </span>
              <span className="text-primary">
                {leadOf(b)}
                {b.text}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    );

  return (
    <div
      role="region"
      aria-label={t("trace.title", { n: para + 1 })}
      className="ml-8 flex flex-col gap-1.5 rounded-md border bg-muted/40 px-3 py-2 text-sm"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium">{t("trace.title", { n: para + 1 })}</span>
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto size-6"
          aria-label={t("trace.close")}
          onClick={onClose}
        >
          <X aria-hidden />
        </Button>
      </div>
      {body}
    </div>
  );
}
