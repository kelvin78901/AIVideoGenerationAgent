import { useTranslation } from "react-i18next";

import type { ComponentMetrics, SpeedMetrics } from "@/api/schemas/metrics";
import { XLabels } from "@/components/charts/axis";
import { ChartCard, ChartTable, Legend } from "@/components/charts/ChartCard";
import { HBar } from "@/components/charts/HBar";
import { RangeDot } from "@/components/charts/RangeDot";
import { niceTicks, percentScale } from "@/components/charts/scale";
import { formatPrice } from "@/lib/cost";
import { useDashboardMessage } from "@/pages/dashboard/format";

const LOCAL = "var(--chart-seq-1)";
const API = "var(--chart-1)";
const minutes = (s: number) => Math.round(s / 60);

/** 各组件累计计算时长: local vs waiting on an API, longest first. */
export function Components({ data }: { data: ComponentMetrics }) {
  const { t } = useTranslation("dashboard");
  const { t: te } = useTranslation("enums");
  const name = (id: string) => te(`component.${id}` as "component.enrich", { defaultValue: id });
  const rows = data.rows
    .map((r) => ({
      ...r,
      local: minutes(r.local_seconds),
      api: minutes(r.api_seconds),
      total: minutes(r.local_seconds + r.api_seconds),
    }))
    .sort((a, b) => b.total - a.total);
  const max = Math.max(1, ...rows.map((r) => r.total));
  const sum = (k: "local" | "api") => rows.reduce((n, r) => n + r[k], 0);

  return (
    <ChartCard
      className="flex-[1_1_440px]"
      title={t("components.title")}
      subtitle={t("components.subtitle", { local: sum("local"), api: sum("api") })}
      legend={
        <Legend
          items={[
            { key: "local", label: t("components.local"), color: LOCAL },
            { key: "api", label: t("components.api"), color: API },
          ]}
        />
      }
      chart={
        <ul className="flex flex-col gap-1.5">
          {rows.map((r) => (
            <li
              key={r.component}
              className="grid min-h-6 grid-cols-[128px_minmax(0,1fr)_48px] items-center gap-2.5 text-[13px]"
            >
              <span className="truncate">{name(r.component)}</span>
              <HBar
                max={max}
                label={t("components.aria", {
                  name: name(r.component),
                  local: r.local,
                  api: r.api,
                })}
                segments={[
                  { key: "local", value: r.local, color: LOCAL },
                  { key: "api", value: r.api, color: API },
                ]}
              />
              <span className="tabular-nums">{r.total}</span>
            </li>
          ))}
        </ul>
      }
      table={
        <ChartTable
          label={t("components.title")}
          minWidth={320}
          columns={[
            { key: "name", label: t("components.col.name") },
            { key: "local", label: t("components.local") },
            { key: "api", label: t("components.api") },
            { key: "total", label: t("components.col.total") },
          ]}
          rows={rows.map((r) => ({
            key: r.component,
            cells: [name(r.component), r.local, r.api, r.total],
          }))}
        />
      }
    />
  );
}

/** 出 1 秒成片要算多少秒: median dot on a fastest–slowest line, per video model and place. */
export function Speed({ data }: { data: SpeedMetrics }) {
  const { t } = useTranslation("dashboard");
  const { t: te } = useTranslation("enums");
  const { t: tc } = useTranslation("components");
  const message = useDashboardMessage();
  const { ticks, top } = niceTicks(Math.max(0, ...data.rows.map((r) => r.max)), 4);
  const x = percentScale([0, top]);
  /** "4 秒约 7.5 分钟": the median applied to a typical shot, rounded to half minutes. */
  const example = (median: number) => {
    const m = Math.round(((median * data.example_output_s) / 60) * 2) / 2;
    return t("speed.example", { s: data.example_output_s, m });
  };
  const where = (r: SpeedMetrics["rows"][number]) =>
    `${te(`where.${r.where}`)} · ${r.price ? formatPrice(tc, r.price) : t("speed.free")}`;

  return (
    <ChartCard
      className="flex-[1_1_440px]"
      title={t("speed.title")}
      subtitle={t("speed.subtitle")}
      chart={
        <div className="flex flex-col gap-1">
          {data.rows.map((r) => (
            <div
              key={`${r.model}-${r.where}`}
              className="grid min-h-13 grid-cols-[150px_minmax(0,1fr)_96px] items-center gap-3"
            >
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-[13px] font-medium">{r.model}</span>
                <span className="text-[11px] text-muted-foreground">{where(r)}</span>
              </span>
              <RangeDot
                min={r.min}
                max={r.max}
                median={r.median}
                domainMax={top}
                label={t("speed.aria", {
                  model: r.model,
                  where: te(`where.${r.where}`),
                  median: r.median,
                  min: r.min,
                  max: r.max,
                })}
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-[13px] tabular-nums">
                  {t("speed.median", { n: r.median })}
                </span>
                <span className="text-[11px] text-muted-foreground">{example(r.median)}</span>
              </span>
            </div>
          ))}
          <div className="grid grid-cols-[150px_minmax(0,1fr)_96px] gap-3">
            <span />
            <XLabels
              ticks={ticks.map((v) => ({ value: v, label: String(v) }))}
              x={x}
              marginLeft={0}
            />
            <span className="text-[11px] text-muted-foreground">{t("speed.unit")}</span>
          </div>
          {data.notes.map((m) => (
            <p key={m.code} className="text-xs leading-relaxed text-muted-foreground">
              {message("speed.note", m)}
            </p>
          ))}
        </div>
      }
      table={
        <ChartTable
          label={t("speed.title")}
          minWidth={360}
          columns={[
            { key: "model", label: t("speed.col.model") },
            { key: "median", label: t("speed.col.median") },
            { key: "min", label: t("speed.col.min") },
            { key: "max", label: t("speed.col.max") },
            { key: "samples", label: t("speed.col.samples") },
          ]}
          rows={data.rows.map((r) => ({
            key: `${r.model}-${r.where}`,
            cells: [
              t("speed.modelWhere", { model: r.model, where: te(`where.${r.where}`) }),
              t("speed.seconds", { n: r.median }),
              t("speed.seconds", { n: r.min }),
              t("speed.seconds", { n: r.max }),
              t("speed.samples", { n: r.samples }),
            ],
          }))}
        />
      }
    />
  );
}
