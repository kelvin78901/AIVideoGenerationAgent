/** 素材整理与同步 (prototype Sync.dc.html; SPEC 14). */
import { ExternalLink, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useEpisodes, useSeries } from "@/api/hooks/series";
import {
  useStartSync,
  useSyncBoard,
  useSyncLog,
  useSyncRun,
  useSyncSettings,
} from "@/api/hooks/sync";
import type { Message } from "@/api/schemas/common";
import { DEMO_SERIES } from "@/app/paths";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { Button } from "@/components/ui/button";
import { formatTime } from "@/lib/format";
import { Board } from "@/pages/sync/Board";
import { Rules } from "@/pages/sync/Rules";
import { Targets } from "@/pages/sync/Targets";

export default function SyncPage() {
  const { t } = useTranslation("sync");
  const { t: tc } = useTranslation();
  const seriesId = useParams().series ?? DEMO_SERIES;
  const series = useSeries(seriesId);
  const episodes = useEpisodes(seriesId);
  const first = episodes.data?.[0];
  const settings = useSyncSettings();
  const board = useSyncBoard(first?.id);
  const run = useSyncRun().data;
  const start = useStartSync();
  const running = run?.state === "running" || start.isPending;

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-5 px-7 pt-6 pb-12">
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        lead={t("lead")}
        className="items-end"
        actions={
          <>
            {board.data ? (
              <Button variant="outline" size="lg" asChild>
                <a href={board.data.comfy_url} target="_blank" rel="noreferrer">
                  <ExternalLink aria-hidden />
                  {t("openComfy")}
                </a>
              </Button>
            ) : null}
            <Button
              size="lg"
              disabled={!first || running}
              onClick={() =>
                first &&
                start.mutate(first.id, { onError: (err) => toast.error(errorMessage(tc, err)) })
              }
            >
              <RefreshCw aria-hidden className={running ? "animate-spin" : undefined} />
              {run?.state === "running"
                ? t("syncing", { done: run.done, total: run.total })
                : t("syncNow")}
            </Button>
          </>
        }
      />

      <QueryState query={settings} skeleton={<Skeleton className="h-48 w-full" />}>
        {(s) => <Targets targets={s.targets} series={series.data?.title ?? ""} />}
      </QueryState>

      <section
        aria-labelledby="board-title"
        className="flex flex-col gap-3 rounded-xl border bg-card p-4.5"
      >
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
          <h2 id="board-title" className="text-base font-bold">
            {t("board.title", { n: first?.idx ?? 1 })}
          </h2>
          <span className="text-xs text-muted-foreground">{t("board.hint")}</span>
        </div>
        <QueryState query={board} skeleton={<Skeleton className="h-[640px] w-full" />}>
          {(b) => <Board board={b} defaultNode="kf103" />}
        </QueryState>
      </section>

      <div className="flex flex-wrap items-start gap-5">
        <QueryState query={settings} skeleton={<Skeleton className="h-96 flex-[999_1_480px]" />}>
          {(s) => <Rules settings={s} />}
        </QueryState>
        <SyncLog seriesId={seriesId} />
      </div>
    </div>
  );
}

function SyncLog({ seriesId }: { seriesId: string }) {
  const { t } = useTranslation("sync");
  const log = useSyncLog(seriesId);
  const msg = (scope: "what" | "target", m: Message) =>
    t(`log.${scope}.${m.code}` as "log.what.manual", { ...m.params, defaultValue: m.code });

  return (
    <aside
      aria-labelledby="sync-log-title"
      className="flex min-w-0 flex-[1_1_320px] flex-col gap-3 rounded-xl border bg-card p-4.5"
    >
      <h2 id="sync-log-title" className="text-base font-bold">
        {t("log.title")}
      </h2>
      <QueryState query={log} skeleton={<Skeleton className="h-40 w-full" />}>
        {(entries) =>
          entries.length ? (
            <ol aria-label={t("log.title")} className="flex flex-col gap-2.5">
              {entries.map((e) => (
                <li key={e.id} className="flex gap-2.5 text-[13px] leading-relaxed">
                  <span className="shrink-0 font-mono text-muted-foreground">
                    {formatTime(e.at)}
                  </span>
                  <span>
                    <span className="font-medium">{msg("what", e.what)}</span>
                    <br />
                    <span className="text-muted-foreground">
                      {t("log.to", { list: e.to.map((m) => msg("target", m)).join(" · ") })}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">{t("log.empty")}</p>
          )
        }
      </QueryState>
      <div className="flex flex-col gap-1.5 rounded-lg bg-accent p-3 text-[13px] leading-relaxed">
        <b className="font-bold">{t("mapping.title")}</b>
        <span>{t("mapping.canvas")}</span>
        <span>{t("mapping.saveBack")}</span>
        <span className="text-muted-foreground">{t("mapping.later")}</span>
      </div>
    </aside>
  );
}
