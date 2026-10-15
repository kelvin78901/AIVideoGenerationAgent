/** 数据看板 (prototype Dashboard.dc.html; SPEC 11). */
import { Download } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import {
  useApiMetrics,
  useCallsSeries,
  useComponentMetrics,
  useEpisodeMetrics,
  useExportCsv,
  useLocalModelMetrics,
  useMetricsKpis,
  useQaMetrics,
  useShotMetrics,
  useSpeedMetrics,
  useSpendSeries,
} from "@/api/hooks/metrics";
import { useEpisodes, useMetricsSummary, useRouteEpisode } from "@/api/hooks/series";
import type { MetricsScope } from "@/api/schemas/metrics";
import { PageHeader } from "@/components/PageHeader";
import { QueryState, Skeleton } from "@/components/QueryState";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/ui/button";
import { formatTime } from "@/lib/format";
import { Budget } from "@/pages/dashboard/Budget";
import { Components, Speed } from "@/pages/dashboard/Compute";
import { Kpis } from "@/pages/dashboard/Kpis";
import { Shots } from "@/pages/dashboard/Shots";
import { SpendAndCalls } from "@/pages/dashboard/SpendAndCalls";
import { Apis, Episodes, LocalModels, Qa } from "@/pages/dashboard/Tables";

export default function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const { t: tc } = useTranslation();
  const { seriesId, episode } = useRouteEpisode();
  const episodes = useEpisodes(seriesId).data ?? [];
  const [scope, setScope] = useState<MetricsScope>("episode");
  const id = scope === "episode" ? episode?.id : seriesId;

  const summary = useMetricsSummary(scope, id);
  const kpis = useMetricsKpis(scope, id);
  const spend = useSpendSeries(scope, id);
  const calls = useCallsSeries(scope, id);
  const shots = useShotMetrics(scope, id);
  const components = useComponentMetrics(scope, id);
  const speed = useSpeedMetrics(scope, id);
  const apis = useApiMetrics(scope, id);
  const localModels = useLocalModelMetrics(scope, id);
  const qa = useQaMetrics(scope, id);
  const episodeRows = useEpisodeMetrics(seriesId);
  const exportCsv = useExportCsv();

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
        actions={
          <Button
            variant="outline"
            size="lg"
            disabled={!id || exportCsv.isPending}
            onClick={() =>
              id &&
              exportCsv.mutate(
                { scope, id },
                {
                  onSuccess: () => toast.success(t("export.done")),
                  onError: (err) => toast.error(errorMessage(tc, err)),
                },
              )
            }
          >
            <Download aria-hidden />
            {t("export.button")}
          </Button>
        }
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

      <QueryState query={shots} skeleton={<Skeleton className="h-96 w-full" />}>
        {(d) => <Shots data={d} />}
      </QueryState>

      <div className="flex flex-wrap items-stretch gap-5">
        <QueryState query={components} skeleton={<Skeleton className="h-80 flex-[1_1_440px]" />}>
          {(d) => <Components data={d} />}
        </QueryState>
        <QueryState query={speed} skeleton={<Skeleton className="h-80 flex-[1_1_440px]" />}>
          {(d) => <Speed data={d} />}
        </QueryState>
      </div>

      <QueryState query={apis} skeleton={<Skeleton className="h-96 w-full" />}>
        {(d) => <Apis data={d} />}
      </QueryState>

      <div className="flex flex-wrap items-stretch gap-5">
        <QueryState query={localModels} skeleton={<Skeleton className="h-80 flex-[1.3_1_480px]" />}>
          {(d) => <LocalModels data={d} />}
        </QueryState>
        <QueryState query={qa} skeleton={<Skeleton className="h-80 flex-[1_1_340px]" />}>
          {(d) => <Qa data={d} />}
        </QueryState>
      </div>

      <QueryState query={episodeRows} skeleton={<Skeleton className="h-48 w-full" />}>
        {(d) => <Episodes data={d} highlight={scope === "series"} />}
      </QueryState>
    </div>
  );
}
