import { useTranslation } from "react-i18next";

import type { MetricsSummary } from "@/api/schemas/metrics";
import { Legend } from "@/components/charts/ChartCard";
import { Meter } from "@/components/charts/Meter";
import { formatUsd } from "@/lib/format";
import { useDashboardMessage } from "@/pages/dashboard/format";

const usd = (v: number) => formatUsd(v, { cents: !Number.isInteger(v) });

/** 预算卡: hero spend, spent + projected-remaining on the budget track, and 「值得注意」. */
export function Budget({ summary }: { summary: MetricsSummary }) {
  const { t } = useTranslation("dashboard");
  const message = useDashboardMessage();
  const { scope, spent_usd: spent, projected_usd: projected, budget_usd: budget } = summary;
  const remain = Math.max(0, projected - spent);
  const max = Math.max(budget ?? 0, projected, spent) || 1;
  const values = { spent: usd(spent), projected: usd(projected), budget: usd(budget ?? 0) };

  return (
    <section
      aria-label={t("budget.region")}
      className="flex flex-wrap items-start gap-x-8 gap-y-5 rounded-xl border bg-card p-5"
    >
      <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-3">
        <div className="text-[13px] text-muted-foreground">{t(`budget.label.${scope}`)}</div>
        <div className="flex flex-wrap items-baseline gap-3">
          <span data-testid="hero-spent" className="text-[52px] leading-none font-bold">
            {values.spent}
          </span>
          <span className="text-[15px] text-muted-foreground">
            {budget != null
              ? t(`budget.of.${scope}`, values)
              : t(`budget.ofNoBudget.${scope}`, values)}
          </span>
        </div>
        <Meter
          size="lg"
          max={max}
          label={
            budget != null ? t(`budget.aria.${scope}`, values) : t(`budget.ariaNoBudget`, values)
          }
          segments={[
            { key: "spent", value: spent, color: "var(--chart-1)" },
            { key: "remain", value: remain, color: "var(--chart-seq-1)" },
          ]}
        />
        <div className="flex flex-wrap items-center gap-x-4.5 gap-y-1.5">
          <Legend
            className="text-[13px]"
            items={[
              {
                key: "spent",
                label: t("budget.spent", { v: values.spent }),
                color: "var(--chart-1)",
              },
              {
                key: "remain",
                label: t("budget.remain", { v: usd(remain) }),
                color: "var(--chart-seq-1)",
              },
              ...(budget != null
                ? [
                    {
                      key: "budget",
                      label: t("budget.budget", { v: values.budget }),
                      color: "var(--chart-track)",
                      outline: true,
                    },
                  ]
                : []),
            ]}
          />
          {budget != null ? (
            <span className="text-[13px] font-medium">
              {projected <= budget
                ? t("budget.within", { v: usd(budget - projected) })
                : t("budget.over", { v: usd(projected - budget) })}
            </span>
          ) : null}
        </div>
      </div>
      <div className="flex min-w-0 flex-[1_1_340px] flex-col gap-2.5">
        <h2 className="text-[13px] font-bold">{t("insights.title")}</h2>
        <ul className="flex flex-col gap-2.5">
          {summary.insights.map((m) => (
            <li key={m.code} className="flex gap-2.5 text-sm leading-[1.7]">
              <span aria-hidden className="mt-2.5 size-1.5 shrink-0 rounded-full bg-foreground" />
              <span>{message("insight", m)}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
