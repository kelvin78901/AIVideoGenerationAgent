/** 数据看板 (prototype Dashboard.dc.html; SPEC 11). */
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useCallsSeries, useMetricsKpis, useSpendSeries } from "@/api/hooks/metrics";
import { useEpisodes, useMetricsSummary, useRouteEpisode } from "@/api/hooks/series";
import type { MetricsScope } from "@/api/schemas/metrics";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { SegmentedControl } from "@/components/SegmentedControl";
import { formatTime } from "@/lib/format";
import { Budget } from "@/pages/dashboard/Budget";
import { Kpis } from "@/pages/dashboard/Kpis";
import { SpendAndCalls } from "@/pages/dashboard/SpendAndCalls";

export default function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const { seriesId, episode } = useRouteEpisode();
  const episodes = useEpisodes(seriesId).data ?? [];
  const [scope, setScope] = useState<MetricsScope>("episode");
  const id = scope === "episode" ? episode?.id : seriesId;

  const summary = useMetricsSummary(scope, id);
  const kpis = useMetricsKpis(scope, id);
  const spend = useSpendSeries(scope, id);
  const calls = useCallsSeries(scope, id);

  const running = episodes.filter((e) => e.stage === "in_progress");
  const scopeNote =
    scope === "episode"
      ? episode
        ? t("scope.noteEpisode", {
            n: episode.idx,
            title: episode.title,
            from: episode.scene_from,
            to: episode.scene_to,
            shots: episode.shot_count ?? 0,
          })
        : ""
      : running.length === 1 && running[0]
        ? t("scope.noteSeriesOne", { episodes: episodes.length, n: running[0].idx })
        : t("scope.noteSeries", { episodes: episodes.length });

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-5 px-7 pt-6 pb-12">
      <PageHeader
        title={t("title")}
        lead={t("lead", {
          time: summary.data ? formatTime(summary.data.updated_at) : "—",
        })}
        className="items-end"
      />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
        <span className="text-[13px] text-muted-foreground">{t("scope.label")}</span>
        <SegmentedControl
          label={t("scope.label")}
          value={scope}
          onChange={setScope}
          options={[
            { value: "episode", label: t("scope.episode", { n: episode?.idx ?? 1 }) },
            { value: "series", label: t("scope.series") },
          ]}
        />
        <span className="text-xs text-muted-foreground">{scopeNote}</span>
      </div>

      <QueryState query={summary} skeleton={<Skeleton className="h-52 w-full" />}>
        {(s) => <Budget summary={s} />}
      </QueryState>

      <QueryState query={kpis} skeleton={<Skeleton className="h-36 w-full" />}>
        {(k) => <Kpis kpis={k} />}
      </QueryState>

      <QueryState query={spend} skeleton={<Skeleton className="h-96 w-full" />}>
        {(sp) => (
          <QueryState query={calls} skeleton={<Skeleton className="h-96 w-full" />}>
            {(cl) => <SpendAndCalls spend={sp} calls={cl} />}
          </QueryState>
        )}
      </QueryState>
    </div>
  );
}
