import { CircleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  CALL_KINDS,
  type CallKind,
  type CallsSeries,
  type SpendSeries,
} from "@/api/schemas/metrics";

import { ChartCard, ChartTable, Legend, Readout } from "@/components/charts/ChartCard";
import { CumulativeChart } from "@/components/charts/CumulativeChart";
import { StackedColumns } from "@/components/charts/StackedColumns";
import { niceTicks, type Tick } from "@/components/charts/scale";
import { formatTime, formatUsd } from "@/lib/format";
import { minutesBetween, timeRange, useDashboardMessage } from "@/pages/dashboard/format";

/** Categorical slots in fixed order (SPEC 11.3): text blue, image orange, audio / video aqua. */
const KIND_COLOR: Record<CallKind, string> = {
  text: "var(--chart-1)",
  image: "var(--chart-2)",
  av: "var(--chart-3)",
};

const money = (v: number) => formatUsd(v, { cents: true });
const moneyTick = (v: number) => formatUsd(v);

/**
 * 累计花费 and 调用次数 side by side. They share one hover: pointing at a bucket in either chart
 * moves the crosshair, highlights the column and updates both readouts (SPEC 11.3).
 */
export function SpendAndCalls({ spend, calls }: { spend: SpendSeries; calls: CallsSeries }) {
  const [hover, setHover] = useState<number | null>(null);
  const clear = () => setHover(null);
  return (
    <div className="flex flex-wrap items-stretch gap-5">
      <SpendCard spend={spend} hover={hover} onHover={setHover} onLeave={clear} />
      <CallsCard calls={calls} spend={spend} hover={hover} onHover={setHover} onLeave={clear} />
    </div>
  );
}

interface Linked {
  hover: number | null;
  onHover: (i: number | null) => void;
  onLeave: () => void;
}

function SpendCard({ spend, hover, onHover, onLeave }: { spend: SpendSeries } & Linked) {
  const { t } = useTranslation("dashboard");
  const message = useDashboardMessage();
  const items = (i: number) =>
    (spend.buckets[i]?.items ?? []).map((m) => message("spend.item", m)).join(t("spend.sep"));

  const at = (iso: string) => minutesBetween(spend.start, iso);
  const xMax = at(spend.end);
  const last = spend.buckets.at(-1);
  const nowValue = last?.cum_usd ?? 0;
  const { ticks, top } = niceTicks(Math.max(spend.budget_usd ?? 0, spend.projected_usd, nowValue));
  const yTicks: Tick[] = ticks.map((v) => ({ value: v, label: moneyTick(v) }));
  const xTicks: Tick[] = [];
  for (let m = 0; m <= xMax; m += 60)
    xTicks.push({
      value: m,
      label: formatTime(new Date(new Date(spend.start).getTime() + m * 60000).toISOString()),
    });

  const ri = hover ?? spend.buckets.length - 1;
  const rb = spend.buckets[ri];

  return (
    <ChartCard
      className="flex-[1_1_460px]"
      onPointerLeave={onLeave}
      title={t("spend.title")}
      subtitle={t("spend.subtitle", { start: formatTime(spend.start) })}
      chart={
        <>
          <CumulativeChart
            xDomain={[0, xMax]}
            yMax={top * 1.07}
            xTicks={xTicks}
            yTicks={yTicks}
            points={[{ x: 0, y: 0 }, ...spend.buckets.map((b) => ({ x: at(b.end), y: b.cum_usd }))]}
            now={{ x: at(spend.now), y: nowValue, label: t("spend.now", { v: money(nowValue) }) }}
            projection={{
              x: xMax,
              y: spend.projected_usd,
              label: t("spend.projected", { v: money(spend.projected_usd) }),
            }}
            budget={
              spend.budget_usd != null
                ? {
                    y: spend.budget_usd,
                    label: t("spend.budget", { v: moneyTick(spend.budget_usd) }),
                  }
                : undefined
            }
            strips={spend.buckets.map((b) => ({
              x0: at(b.start),
              x1: at(b.end),
              point: { x: at(b.end), y: b.cum_usd },
              label: t("spend.strip", {
                range: timeRange(b.start, b.end),
                add: money(b.add_usd),
                cum: money(b.cum_usd),
              }),
            }))}
            hover={hover}
            onHover={onHover}
          />
          {rb ? (
            <Readout title={readoutTitle(t, rb, hover == null)}>
              {t("spend.readout", {
                add: money(rb.add_usd),
                cum: money(rb.cum_usd),
                items: items(ri),
              })}
            </Readout>
          ) : null}
        </>
      }
      table={
        <ChartTable
          label={t("spend.title")}
          minWidth={520}
          columns={[
            { key: "time", label: t("table.time"), className: "w-24" },
            { key: "add", label: t("spend.table.add"), className: "w-18" },
            { key: "cum", label: t("spend.table.cum"), className: "w-18" },
            { key: "items", label: t("spend.table.items"), className: "text-muted-foreground" },
          ]}
          rows={spend.buckets.map((b, i) => ({
            key: b.start,
            cells: [timeRange(b.start, b.end), money(b.add_usd), money(b.cum_usd), items(i)],
          }))}
        />
      }
    />
  );
}

function CallsCard({
  calls,
  spend,
  hover,
  onHover,
  onLeave,
}: { calls: CallsSeries; spend: SpendSeries } & Linked) {
  const { t } = useTranslation("dashboard");
  const kind = (k: CallKind) => t(`kind.${k}`);
  const totals = calls.buckets.map((b) => CALL_KINDS.reduce((n, k) => n + b.counts[k], 0));
  const maxTotal = Math.max(0, ...totals);
  const { ticks, top } = niceTicks(maxTotal);
  const counts = (i: number) => {
    const b = calls.buckets[i];
    if (!b) return "";
    const parts = CALL_KINDS.map((k) => t("calls.kindCount", { kind: kind(k), n: b.counts[k] }));
    if (b.failed) parts.push(t("calls.failedCount", { n: b.failed }));
    return parts.join(t("spend.sep"));
  };

  const ri = hover ?? calls.buckets.length - 1;
  const rb = calls.buckets[ri];

  return (
    <ChartCard
      className="flex-[1_1_420px]"
      onPointerLeave={onLeave}
      title={t("calls.title", { m: calls.bucket_minutes })}
      subtitle={t("calls.subtitle", { n: calls.calls, ok: calls.succeeded })}
      legend={
        <Legend
          items={calls.totals.map((x) => ({
            key: x.kind,
            color: KIND_COLOR[x.kind],
            label: t("calls.legend", { kind: kind(x.kind), n: x.calls, cost: money(x.cost_usd) }),
          }))}
        />
      }
      chart={
        <>
          <StackedColumns
            yMax={top}
            yTicks={ticks.map((v) => ({ value: v, label: String(v) }))}
            hover={hover}
            onHover={onHover}
            columns={calls.buckets.map((b, i) => ({
              key: b.start,
              segments: CALL_KINDS.map((k) => ({
                key: k,
                value: b.counts[k],
                color: KIND_COLOR[k],
              })),
              label: t("calls.column", { range: timeRange(b.start, b.end), counts: counts(i) }),
              xLabel: i % 2 === 0 ? formatTime(b.start) : "",
              top:
                b.failed || (totals[i] === maxTotal && maxTotal > 0) ? (
                  <span className="flex flex-col items-center gap-1">
                    {b.failed ? (
                      <span className="inline-flex items-center gap-0.5 whitespace-nowrap">
                        <CircleAlert aria-hidden className="size-3.5 text-status-fail" />
                        {t("calls.failed", { n: b.failed })}
                      </span>
                    ) : null}
                    {totals[i] === maxTotal ? <span>{totals[i]}</span> : null}
                  </span>
                ) : undefined,
            }))}
          />
          {rb ? (
            <Readout title={readoutTitle(t, rb, hover == null)}>
              {t("calls.readout", {
                counts: counts(ri),
                cost: money(spend.buckets[ri]?.add_usd ?? rb.cost_usd),
              })}
            </Readout>
          ) : null}
        </>
      }
      table={
        <ChartTable
          label={t("calls.title", { m: calls.bucket_minutes })}
          columns={[
            { key: "time", label: t("table.time"), className: "w-24" },
            ...CALL_KINDS.map((k) => ({ key: k, label: kind(k) })),
            { key: "failed", label: t("calls.table.failed") },
          ]}
          rows={calls.buckets.map((b) => ({
            key: b.start,
            cells: [timeRange(b.start, b.end), ...CALL_KINDS.map((k) => b.counts[k]), b.failed],
          }))}
        />
      }
    />
  );
}

function readoutTitle(
  t: ReturnType<typeof useTranslation<"dashboard">>["t"],
  b: { start: string; end: string },
  latest: boolean,
) {
  return `${timeRange(b.start, b.end)}${latest ? t("readout.latest") : ""}`;
}
