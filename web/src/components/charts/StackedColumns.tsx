import type { ReactNode } from "react";

import { YGrid } from "@/components/charts/axis";
import { percentScale, type Tick } from "@/components/charts/scale";
import { cn } from "@/lib/utils";

export interface ColumnSegment {
  key: string;
  value: number;
  /** CSS colour (a `var(--chart-*)` token). */
  color: string;
}

export interface Column {
  key: string;
  /** Bottom → top. Zero segments are skipped. */
  segments: ColumnSegment[];
  /** Accessible name: the bucket and every value in words. */
  label: string;
  /** X label under the column; empty to skip (label every other column when crowded). */
  xLabel?: string;
  /** Shown above the column (a total on the tallest one, a failure marker …). */
  top?: ReactNode;
}

/** Bars are capped at 20px (SPEC 11.3: ≤ 24); the leftover band is air. */
export const COLUMN_WIDTH = 20;
const GAP = 2;

/**
 * Stacked columns, one per bucket: 4px rounded data-end on the top segment, square at the
 * baseline, a 2px card-coloured gap between segments. Each column is a button and its own hover
 * target; the hovered one gets a soft backdrop. Hover is owned by the caller (linked charts).
 */
export function StackedColumns({
  columns,
  yMax,
  yTicks,
  hover,
  onHover,
  height = 196,
  marginLeft = 28,
}: {
  columns: Column[];
  yMax: number;
  yTicks: Tick[];
  hover: number | null;
  onHover: (i: number | null) => void;
  height?: number;
  marginLeft?: number;
}) {
  const y = percentScale([0, yMax], true);
  const px = (v: number) => (v / yMax) * height;

  return (
    <div>
      <div className="relative" style={{ height, margin: `8px 0 0 ${marginLeft}px` }}>
        <YGrid ticks={yTicks} y={y} labelWidth={marginLeft} />
        <div className="absolute inset-0 flex items-stretch">
          {columns.map((c, i) => {
            const segs = c.segments.filter((s) => s.value > 0);
            return (
              <button
                key={c.key}
                type="button"
                aria-label={c.label}
                aria-pressed={hover === i}
                data-column
                onPointerEnter={() => onHover(i)}
                onFocus={() => onHover(i)}
                onClick={() => onHover(i)}
                className={cn(
                  "relative flex h-full min-w-0 flex-1 flex-col-reverse items-center gap-0.5 rounded p-0 outline-none",
                  "focus-visible:ring-2 focus-visible:ring-ring",
                  hover === i && "bg-accent/70",
                )}
              >
                {segs.map((s, j) => (
                  <span
                    key={s.key}
                    data-segment={s.key}
                    className={cn("block shrink-0", j === segs.length - 1 && "rounded-t")}
                    style={{
                      width: COLUMN_WIDTH,
                      height: Math.max(1, px(s.value) - GAP),
                      background: s.color,
                    }}
                  />
                ))}
                {c.top ? <span className="mb-0.5 text-[11px] font-medium">{c.top}</span> : null}
              </button>
            );
          })}
        </div>
      </div>
      <div aria-hidden data-axis="x" className="flex h-[18px]" style={{ marginLeft }}>
        {columns.map((c) => (
          <span
            key={c.key}
            className="min-w-0 flex-1 text-center text-[11px] text-muted-foreground tabular-nums"
          >
            {c.xLabel}
          </span>
        ))}
      </div>
    </div>
  );
}
