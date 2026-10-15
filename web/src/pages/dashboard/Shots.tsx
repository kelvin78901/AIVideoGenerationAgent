import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  SHOT_STAGES,
  type ShotMetric,
  type ShotMetrics,
  type ShotMetricStatus,
  type ShotStage,
} from "@/api/schemas/metrics";
import { ChartCard, ChartTable, Legend, Readout } from "@/components/charts/ChartCard";
import { HBar } from "@/components/charts/HBar";
import { niceTicks } from "@/components/charts/scale";
import { StatusBadge, type Tone } from "@/components/StatusBadge";
import { formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useDashboardMessage } from "@/pages/dashboard/format";

/** Ordered stages → the sequential ramp, light to dark (SPEC 11.3). */
const STAGE_COLOR: Record<ShotStage, string> = {
  kf: "var(--chart-seq-1)",
  vid: "var(--chart-seq-2)",
  post: "var(--chart-seq-3)",
};

const STATUS_TONE: Record<ShotMetricStatus, Tone> = {
  adopted: "info",
  picking: "warn",
  generating: "neutral",
  queued: "neutral",
  waiting: "neutral",
};

const GRID = "grid grid-cols-[170px_minmax(0,1fr)_60px_52px_64px_72px] gap-3";
const minutes = (s: number) => Math.round(s / 60);
const total = (x: ShotMetric) => SHOT_STAGES.reduce((n, k) => n + x.stage_seconds[k], 0);
const money = (v: number) => formatUsd(v, { cents: true });

/** 每个镜头花了多少时间和钱: per-scene groups, stage bars, click a row for the details. */
export function Shots({ data }: { data: ShotMetrics }) {
  const { t } = useTranslation("dashboard");
  const message = useDashboardMessage();
  const initial = data.shots.find((x) => x.status === "picking") ?? data.shots[0];
  const [selected, setSelected] = useState(initial?.shot_id);
  const sel = data.shots.find((x) => x.shot_id === selected) ?? initial;
  const { top } = niceTicks(Math.max(0, ...data.shots.map((x) => minutes(total(x)))), 4);
  const stage = (k: ShotStage) => t(`shots.stage.${k}`);
  const status = (x: ShotMetric) => (
    <StatusBadge tone={STATUS_TONE[x.status]} icon={null}>
      {t(`shots.status.${x.status}`)}
    </StatusBadge>
  );
  const dash = t("kpi.none");

  const note = (x: ShotMetric) =>
    [
      x.notes.map((m) => message("shots.note", m)).join(t("shots.noteSep")),
      x.take_chain.map((m) => message("shots.take", m)).join(" → "),
    ]
      .filter(Boolean)
      .join(t("shots.noteSep")) + t("shots.noteEnd");

  return (
    <ChartCard
      title={t("shots.title")}
      subtitle={t("shots.subtitle")}
      legend={
        <Legend
          items={SHOT_STAGES.map((k) => ({ key: k, label: stage(k), color: STAGE_COLOR[k] }))}
        />
      }
      chart={
        <>
          <div className="overflow-x-auto">
            <div className="flex min-w-[760px] flex-col gap-0.5">
              <div className={cn(GRID, "px-2 py-1 text-xs font-medium text-muted-foreground")}>
                <span>{t("shots.col.shot")}</span>
                <span>{t("shots.col.compute", { max: top })}</span>
                <span>{t("shots.col.total")}</span>
                <span>{t("shots.col.takes")}</span>
                <span>{t("shots.col.cost")}</span>
                <span>{t("shots.col.status")}</span>
              </div>
              {data.scenes.map((sc) => {
                const xs = data.shots.filter((x) => x.scene === sc.scene);
                return (
                  <div key={sc.scene} role="group" aria-label={t("shots.scene", sc)}>
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-chart-grid px-2 pt-2.5 pb-1 text-[13px]">
                      <span className="font-bold">{t("shots.scene", sc)}</span>
                      <span className="text-muted-foreground">
                        {t("shots.sceneSum", {
                          n: xs.length,
                          adopted: xs.filter((x) => x.status === "adopted").length,
                          minutes: minutes(xs.reduce((n, x) => n + total(x), 0)),
                          cost: money(xs.reduce((n, x) => n + x.cost_usd, 0)),
                        })}
                      </span>
                    </div>
                    {xs.map((x) => {
                      const on = x.shot_id === sel?.shot_id;
                      const sum = minutes(total(x));
                      return (
                        <button
                          key={x.shot_id}
                          type="button"
                          aria-pressed={on}
                          onClick={() => setSelected(x.shot_id)}
                          onFocus={() => setSelected(x.shot_id)}
                          className={cn(
                            GRID,
                            "min-h-9 w-full items-center rounded-md px-2 py-1 text-left text-[13px] tabular-nums",
                            "outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            on ? "bg-accent/70" : "hover:bg-muted",
                          )}
                        >
                          <span className="truncate">
                            <span className="font-mono font-medium">{x.shot_id}</span> {x.title}
                          </span>
                          {sum > 0 ? (
                            <HBar
                              max={top}
                              thickness={18}
                              segments={SHOT_STAGES.map((k) => ({
                                key: k,
                                value: minutes(x.stage_seconds[k]),
                                color: STAGE_COLOR[k],
                              }))}
                            />
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              {x.waiting_for ? t("shots.waiting", { shot: x.waiting_for }) : ""}
                            </span>
                          )}
                          <span>{sum ? t("shots.minutes", { n: sum }) : dash}</span>
                          <span>{x.takes || dash}</span>
                          <span>{x.cost_usd ? money(x.cost_usd) : dash}</span>
                          {status(x)}
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
          {sel ? (
            <Readout title={`${sel.shot_id} ${sel.title}`}>
              {t("shots.split", {
                kf: minutes(sel.stage_seconds.kf),
                vid: minutes(sel.stage_seconds.vid),
                post: minutes(sel.stage_seconds.post),
                cost: money(sel.cost_usd),
                takes: sel.takes,
              })}
              <br />
              <span className="text-foreground">{note(sel)}</span>
            </Readout>
          ) : null}
        </>
      }
      table={
        <ChartTable
          label={t("shots.title")}
          minWidth={640}
          columns={[
            { key: "shot", label: t("shots.col.shot") },
            ...SHOT_STAGES.map((k) => ({ key: k, label: stage(k) })),
            { key: "total", label: t("shots.col.total") },
            { key: "takes", label: t("shots.col.takes") },
            { key: "cost", label: t("shots.col.cost") },
            { key: "status", label: t("shots.col.status") },
          ]}
          rows={data.shots.map((x) => ({
            key: x.shot_id,
            cells: [
              x.shot_id,
              ...SHOT_STAGES.map((k) => minutes(x.stage_seconds[k])),
              minutes(total(x)),
              x.takes,
              money(x.cost_usd),
              t(`shots.status.${x.status}`),
            ],
          }))}
        />
      }
    />
  );
}
