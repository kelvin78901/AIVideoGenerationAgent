import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { MetricsKpis } from "@/api/schemas/metrics";
import { Meter } from "@/components/charts/Meter";
import { formatPercent, formatUsd } from "@/lib/format";
import { useDuration } from "@/pages/dashboard/format";

/** The six KPI tiles (SPEC 11.1 `/metrics/kpis`). Success rate = succeeded / (calls − canceled). */
export function Kpis({ kpis: k }: { kpis: MetricsKpis }) {
  const { t } = useTranslation("dashboard");
  const duration = useDuration();
  const attempted = k.api_calls - k.api_canceled;
  const rate = formatPercent(attempted > 0 ? k.api_succeeded / attempted : 1);
  const money = (v: number) => formatUsd(v, { cents: true });

  return (
    <section
      aria-label={t("kpi.region")}
      className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3"
    >
      <Tile
        label={t("kpi.adopted.label")}
        value={t("kpi.adopted.value", { n: k.adopted_seconds })}
        meter={k.total_seconds > 0 ? { value: k.adopted_seconds, max: k.total_seconds } : undefined}
        sub={t("kpi.adopted.sub", {
          total: k.total_seconds,
          shots: k.shots,
          adopted: k.shots_adopted,
        })}
      />
      <Tile
        label={t("kpi.costPerSecond.label")}
        value={k.cost_per_second_usd != null ? money(k.cost_per_second_usd) : t("kpi.none")}
        sub={
          k.projected_cost_per_second_usd != null
            ? t("kpi.costPerSecond.sub", { v: money(k.projected_cost_per_second_usd) })
            : t("kpi.costPerSecond.empty")
        }
      />
      <Tile
        label={t("kpi.gpu.label")}
        value={duration(k.local_gpu_seconds)}
        sub={
          k.vram_peak_gb != null
            ? t("kpi.gpu.sub", { wait: duration(k.api_wait_seconds), vram: k.vram_peak_gb })
            : t("kpi.gpu.subNoVram", { wait: duration(k.api_wait_seconds) })
        }
      />
      <Tile
        label={t("kpi.calls.label")}
        value={t("kpi.calls.value", { n: k.api_calls })}
        sub={
          k.rate_limit_retries > 0
            ? t("kpi.calls.subRetried", { ok: k.api_succeeded, rate, n: k.rate_limit_retries })
            : t("kpi.calls.sub", { ok: k.api_succeeded, rate })
        }
      />
      <Tile
        label={t("kpi.qa.label")}
        value={t("kpi.qa.value", { passed: k.qa_passed, total: k.qa_total })}
        meter={k.qa_total > 0 ? { value: k.qa_passed, max: k.qa_total } : undefined}
        sub={t("kpi.qa.sub", {
          reruns: k.auto_reruns,
          fallbacks: k.auto_fallbacks,
          manual: k.manual_switches,
        })}
      />
      <Tile
        label={t("kpi.adopt.label")}
        value={
          k.adopt_median_seconds != null
            ? t("kpi.adopt.value", { d: duration(k.adopt_median_seconds) })
            : t("kpi.none")
        }
        sub={
          k.slowest_open
            ? t("kpi.adopt.sub", { shot: k.slowest_open.shot, d: duration(k.slowest_open.seconds) })
            : t("kpi.adopt.allDone")
        }
      />
    </section>
  );
}

function Tile({
  label,
  value,
  sub,
  meter,
}: {
  label: string;
  value: ReactNode;
  sub: ReactNode;
  meter?: { value: number; max: number };
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="flex flex-col gap-1.5 rounded-xl border bg-card px-4 py-3.5"
    >
      <div className="text-[13px] text-muted-foreground">{label}</div>
      <div className="text-[26px] leading-tight font-bold">{value}</div>
      {meter ? (
        <Meter
          size="sm"
          max={meter.max}
          segments={[{ key: "value", value: meter.value, color: "var(--chart-1)" }]}
        />
      ) : null}
      <div className="text-xs leading-relaxed text-muted-foreground">{sub}</div>
    </div>
  );
}
