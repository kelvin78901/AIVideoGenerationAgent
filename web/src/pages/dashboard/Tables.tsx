import { AlertCircle, Check } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type {
  ApiMetrics,
  CallKind,
  EpisodeMetrics,
  LocalModelMetrics,
  QaMetrics,
} from "@/api/schemas/metrics";
import { HBar } from "@/components/charts/HBar";
import { Swatch } from "@/components/charts/ChartCard";
import { Meter } from "@/components/charts/Meter";
import { formatPrice } from "@/lib/cost";
import { formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useDashboardMessage, useDuration } from "@/pages/dashboard/format";

/** Same categorical slots as the calls chart (SPEC 11.3). */
const KIND_COLOR: Record<CallKind, string> = {
  text: "var(--chart-1)",
  image: "var(--chart-2)",
  av: "var(--chart-3)",
};
const money = (v: number) => formatUsd(v, { cents: true });
/** 100% for a clean record, one decimal otherwise ("80.0%", "97.6%"). */
const rate = (ok: number, n: number) =>
  n > 0 ? (ok === n ? "100%" : `${((ok / n) * 100).toFixed(1)}%`) : "—";

function Card({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={title}
      className={cn(
        "flex min-w-0 flex-col gap-2.5 rounded-xl border bg-card px-4.5 py-4",
        className,
      )}
    >
      <div className="flex flex-col gap-0.5">
        <h2 className="text-base font-bold">{title}</h2>
        <span className="text-xs text-muted-foreground">{subtitle}</span>
      </div>
      {children}
    </section>
  );
}

const th = "px-1 py-2 text-left text-xs font-medium text-muted-foreground";
const td = "px-1 py-2 align-middle";

/** 各 API 的调用和花费: a table with an inline cost bar (the table is the chart here). */
export function Apis({ data }: { data: ApiMetrics }) {
  const { t } = useTranslation("dashboard");
  const { t: tc } = useTranslation("components");
  const message = useDashboardMessage();
  const rows = [...data.rows].sort((a, b) => b.cost_usd - a.cost_usd);
  const maxCost = Math.max(0.01, ...rows.map((r) => r.cost_usd));
  const calls = rows.reduce((n, r) => n + r.calls, 0);
  const ok = rows.reduce((n, r) => n + r.succeeded, 0);
  const attempted = rows.reduce((n, r) => n + r.calls - r.canceled, 0);
  const latency = (s: number) =>
    s < 120
      ? t("apis.latencyS", { s: Math.round(s) })
      : t("apis.latencyMs", { m: Math.floor(s / 60), s: Math.round(s % 60) });

  return (
    <Card title={t("apis.title")} subtitle={t("apis.subtitle")}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-[13px] tabular-nums">
          <thead>
            <tr className="border-b">
              <th scope="col" className={th}>
                {t("apis.col.api")}
              </th>
              <th scope="col" className={th}>
                {t("apis.col.kind")}
              </th>
              <th scope="col" className={th}>
                {t("apis.col.calls")}
              </th>
              <th scope="col" className={th}>
                {t("apis.col.rate")}
              </th>
              <th scope="col" className={th}>
                {t("apis.col.latency")}
              </th>
              <th scope="col" className={th}>
                {t("apis.col.usage")}
              </th>
              <th scope="col" className={cn(th, "w-[30%]")}>
                {t("apis.col.cost")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.model} className="border-b border-border/60">
                <td className={td}>
                  <span className="flex flex-col gap-0.5">
                    <span className="font-medium">{r.model}</span>
                    {r.note ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                        <AlertCircle aria-hidden className="size-3 text-status-fail" />
                        {message("apis.note", r.note)}
                      </span>
                    ) : null}
                  </span>
                </td>
                <td className={td}>
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <Swatch color={KIND_COLOR[r.kind]} />
                    {t(`kind.${r.kind}`)}
                  </span>
                </td>
                <td className={td}>{r.calls}</td>
                <td className={td}>{rate(r.succeeded, r.calls - r.canceled)}</td>
                <td className={td}>{latency(r.median_latency_s)}</td>
                <td className={cn(td, "text-xs")}>
                  <span className="flex flex-col gap-0.5">
                    <span>{message("apis.usage", r.usage)}</span>
                    <span className="text-muted-foreground">
                      {r.prices.map((p) => formatPrice(tc, p)).join(t("spend.sep"))}
                    </span>
                  </span>
                </td>
                <td className={td}>
                  <span className="grid grid-cols-[minmax(0,1fr)_92px] items-center gap-2">
                    <HBar
                      max={maxCost}
                      thickness={12}
                      minWidth={0.6}
                      segments={[{ key: "cost", value: r.cost_usd, color: KIND_COLOR[r.kind] }]}
                    />
                    <span className="font-medium">
                      {money(r.cost_usd)}{" "}
                      <span className="font-normal text-muted-foreground">
                        {Math.round((r.cost_usd / data.total_cost_usd) * 100)}%
                      </span>
                    </span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-bold">
              <th scope="row" className={cn(td, "text-left")}>
                {t("apis.total")}
              </th>
              <td className={td} />
              <td className={td}>{calls}</td>
              <td className={td}>{rate(ok, attempted)}</td>
              <td className={td} />
              <td className={td} />
              <td className={td}>{money(data.total_cost_usd)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}

/** 本地模型: runs, time, VRAM peak on a bar whose full width is the machine's VRAM. */
export function LocalModels({ data }: { data: LocalModelMetrics }) {
  const { t } = useTranslation("dashboard");
  const { t: te } = useTranslation("enums");
  const message = useDashboardMessage();
  const duration = useDuration();
  const name = (id: string) => te(`component.${id}` as "component.enrich", { defaultValue: id });

  return (
    <Card
      className="flex-[1.3_1_480px]"
      title={t("local.title")}
      subtitle={t("local.subtitle", { total: data.vram_total_gb })}
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[600px] text-[13px] tabular-nums">
          <thead>
            <tr className="border-b">
              <th scope="col" className={th}>
                {t("local.col.model")}
              </th>
              <th scope="col" className={th}>
                {t("local.col.use")}
              </th>
              <th scope="col" className={th}>
                {t("local.col.runs")}
              </th>
              <th scope="col" className={th}>
                {t("local.col.time")}
              </th>
              <th scope="col" className={cn(th, "w-[32%]")}>
                {t("local.col.vram")}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.model} className="border-b border-border/60">
                <td className={cn(td, "font-medium")}>{r.model}</td>
                <td className={cn(td, "text-xs text-muted-foreground")}>
                  {r.components.map(name).join(t("listSep"))}
                </td>
                <td className={td}>{r.runs}</td>
                <td className={td}>{duration(r.seconds)}</td>
                <td className={td}>
                  <span className="grid grid-cols-[minmax(0,1fr)_64px] items-center gap-2">
                    <Meter
                      max={data.vram_total_gb}
                      label={t("local.vramAria", {
                        model: r.model,
                        peak: r.vram_peak_gb,
                        total: data.vram_total_gb,
                      })}
                      segments={[
                        {
                          key: "vram",
                          value: r.vram_peak_gb,
                          // Near-full peaks take the darkest step so they stand out.
                          color:
                            r.vram_peak_gb / data.vram_total_gb > 0.875
                              ? "var(--chart-seq-3)"
                              : "var(--chart-1)",
                        },
                      ]}
                    />
                    <span className="text-xs">
                      {t("local.gb", { n: r.vram_peak_gb.toFixed(1) })}
                    </span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.notes.map((m) => (
        <p key={m.code} className="text-xs leading-relaxed text-muted-foreground">
          {message("local.note", m)}
        </p>
      ))}
    </Card>
  );
}

/** 自动质检: pass / fail split with icons, the counters and why takes failed. */
export function Qa({ data }: { data: QaMetrics }) {
  const { t } = useTranslation("dashboard");
  const total = data.passed + data.failed;
  const maxIssue = Math.max(1, ...data.issues.map((i) => i.count));

  return (
    <Card
      className="flex-[1_1_340px]"
      title={t("qa.title")}
      subtitle={t("qa.subtitle", { n: total })}
    >
      <div
        role="img"
        aria-label={t("qa.aria", { passed: data.passed, failed: data.failed })}
        className="flex h-3.5 gap-0.5"
      >
        {data.passed ? (
          <span
            className="rounded-l bg-status-pass last:rounded-r"
            style={{ flex: `${data.passed} 1 0` }}
          />
        ) : null}
        {data.failed ? (
          <span
            className="rounded-r bg-status-fail first:rounded-l"
            style={{ flex: `${data.failed} 1 0` }}
          />
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-4.5 gap-y-1.5 text-[13px]">
        <span className="inline-flex items-center gap-1.5">
          <span className="flex size-4 items-center justify-center rounded-full bg-status-pass text-white">
            <Check aria-hidden className="size-3" strokeWidth={3} />
          </span>
          {t("qa.passed", { n: data.passed })}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <AlertCircle aria-hidden className="size-4 text-status-fail" />
          {t("qa.failed", { n: data.failed })}
        </span>
        <span className="text-muted-foreground">
          {t("kpi.qa.sub", {
            reruns: data.auto_reruns,
            fallbacks: data.auto_fallbacks,
            manual: data.manual_switches,
          })}
        </span>
      </div>
      <h3 className="text-[13px] font-medium">{t("qa.why")}</h3>
      <ul className="flex flex-col gap-1.5">
        {data.issues.map((i) => (
          <li
            key={i.issue}
            className="grid grid-cols-[148px_minmax(0,1fr)_24px] items-center gap-2.5 text-[13px]"
          >
            <span>{t(`qa.issue.${i.issue}`)}</span>
            <HBar
              max={maxIssue}
              thickness={14}
              segments={[{ key: "count", value: i.count, color: "var(--chart-1)" }]}
            />
            <span className="tabular-nums">{i.count}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** 按集汇总: one row per episode plus the series total. */
export function Episodes({ data, highlight }: { data: EpisodeMetrics; highlight: boolean }) {
  const { t } = useTranslation("dashboard");
  const duration = useDuration();
  const sum = (f: (r: EpisodeMetrics["rows"][number]) => number) =>
    data.rows.reduce((n, r) => n + f(r), 0);
  const anyEstimated = data.rows.some((r) => r.total_estimated);
  const computed = data.rows.filter((r) => r.compute_seconds != null);
  const len = (adopted: number, total: number, estimated: boolean) =>
    t(estimated ? "episodes.lenEstimated" : "episodes.len", { adopted, total });

  return (
    <Card
      title={t("episodes.title")}
      subtitle={t("episodes.subtitle")}
      className={cn(highlight && "border-2 border-primary")}
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-[13px] tabular-nums">
          <thead>
            <tr className="border-b">
              <th scope="col" className={th}>
                {t("episodes.col.episode")}
              </th>
              <th scope="col" className={th}>
                {t("episodes.col.stage")}
              </th>
              <th scope="col" className={th}>
                {t("episodes.col.len")}
              </th>
              <th scope="col" className={th}>
                {t("episodes.col.spent")}
              </th>
              <th scope="col" className={th}>
                {t("episodes.col.projected")}
              </th>
              <th scope="col" className={th}>
                {t("episodes.col.compute")}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.episode_id} className="border-b border-border/60">
                <th scope="row" className={cn(td, "text-left font-normal")}>
                  {t("episodes.name", { n: r.idx, title: r.title })}
                </th>
                <td className={cn(td, "text-muted-foreground")}>
                  {t(`episodes.stage.${r.stage}`)}
                </td>
                <td className={td}>{len(r.adopted_seconds, r.total_seconds, r.total_estimated)}</td>
                <td className={td}>{formatUsd(r.spent_usd, { cents: r.spent_usd > 0 })}</td>
                <td className={td}>
                  {t(r.reuses_assets ? "episodes.projectedReuse" : "episodes.projected", {
                    v: money(r.projected_usd),
                  })}
                </td>
                <td className={td}>
                  {r.compute_seconds != null ? duration(r.compute_seconds) : t("kpi.none")}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-bold">
              <th scope="row" className={cn(td, "text-left")}>
                {t("episodes.total")}
              </th>
              <td className={td} />
              <td className={td}>
                {len(
                  sum((r) => r.adopted_seconds),
                  sum((r) => r.total_seconds),
                  anyEstimated,
                )}
              </td>
              <td className={td}>{money(sum((r) => r.spent_usd))}</td>
              <td className={td}>
                {t("episodes.projected", { v: money(sum((r) => r.projected_usd)) })}
              </td>
              <td className={td}>
                {computed.length
                  ? duration(computed.reduce((n, r) => n + (r.compute_seconds ?? 0), 0))
                  : t("kpi.none")}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}
