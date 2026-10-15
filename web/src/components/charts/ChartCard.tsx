import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SegmentedControl } from "@/components/SegmentedControl";
import { cn } from "@/lib/utils";

export type ChartView = "chart" | "table";

/**
 * Card around one chart (SPEC 11.3): title, subtitle, the 图 / 表 switch, an optional legend row,
 * then either the chart or its table twin. Both views get the same data from the caller.
 */
export function ChartCard({
  title,
  subtitle,
  legend,
  chart,
  table,
  onPointerLeave,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  legend?: ReactNode;
  chart: ReactNode;
  table: ReactNode;
  /** Clears linked hover state when the pointer leaves the card. */
  onPointerLeave?: () => void;
  className?: string;
}) {
  const { t } = useTranslation("components");
  const [view, setView] = useState<ChartView>("chart");
  const titleId = useId();
  return (
    <section
      aria-labelledby={titleId}
      data-view={view}
      onPointerLeave={onPointerLeave}
      className={cn(
        "flex min-w-0 flex-col gap-2.5 rounded-xl border bg-card px-4.5 py-4",
        className,
      )}
    >
      <div className="flex flex-wrap items-start gap-2">
        <div className="mr-auto flex min-w-0 flex-col gap-0.5">
          <h2 id={titleId} className="text-base font-bold">
            {title}
          </h2>
          {subtitle ? <span className="text-xs text-muted-foreground">{subtitle}</span> : null}
        </div>
        <SegmentedControl
          size="sm"
          label={t("chart.view")}
          value={view}
          onChange={setView}
          options={[
            { value: "chart", label: t("chart.chart") },
            { value: "table", label: t("chart.table") },
          ]}
        />
      </div>
      {legend}
      {view === "chart" ? chart : <div className="overflow-x-auto">{table}</div>}
    </section>
  );
}

export interface LegendItem {
  key: string;
  label: ReactNode;
  /** CSS colour (a `var(--chart-*)` token). */
  color: string;
  /** Rect for bars and areas, line for lines (mirrors the mark). */
  shape?: "rect" | "line";
  /** Draws the swatch as a track outline (e.g. the unfilled budget). */
  outline?: boolean;
}

/** Series legend: always shown for two or more series; text stays in text colours. */
export function Legend({ items, className }: { items: LegendItem[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground", className)}>
      {items.map((i) => (
        <li key={i.key} className="inline-flex items-center gap-1.5">
          <Swatch color={i.color} shape={i.shape} outline={i.outline} />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

export function Swatch({
  color,
  shape = "rect",
  outline,
}: {
  color: string;
  shape?: "rect" | "line";
  outline?: boolean;
}) {
  return (
    <span
      aria-hidden
      data-swatch
      className={cn(
        "inline-block shrink-0",
        shape === "line" ? "h-0.5 w-3 rounded-full" : "size-2.5 rounded-[2px]",
        outline && "ring-1 ring-chart-seq-1 ring-inset",
      )}
      style={{ background: color }}
    />
  );
}

/**
 * The 「悬停」 readout under a chart: the hovered (or latest) bucket in words. It is the chart's
 * tooltip: it never hides anything the table view does not also show.
 */
export function Readout({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div
      data-readout
      className="min-h-11 rounded-lg bg-muted px-2.5 py-2 text-[13px] leading-relaxed"
    >
      <b className="font-bold">{title}</b>
      <span className="text-muted-foreground"> · {children}</span>
    </div>
  );
}

/** Plain table for the 表 view: header row + rows of cells, numbers tabular. */
export function ChartTable({
  columns,
  rows,
  minWidth = 420,
  label,
}: {
  columns: { key: string; label: ReactNode; className?: string }[];
  rows: { key: string; cells: ReactNode[]; strong?: boolean }[];
  minWidth?: number;
  label: string;
}) {
  return (
    <table aria-label={label} className="w-full text-xs tabular-nums" style={{ minWidth }}>
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          {columns.map((c) => (
            <th key={c.key} scope="col" className={cn("px-1 py-1.5 font-medium", c.className)}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className={cn("border-b border-border/60", r.strong && "font-bold")}>
            {r.cells.map((c, i) => (
              <td key={columns[i]?.key ?? i} className={cn("px-1 py-1.5", columns[i]?.className)}>
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
