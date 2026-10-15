/**
 * Axes for HTML-positioned charts: the plot box is `position: relative`, marks are SVG in a
 * stretched viewBox, and ticks / labels are HTML placed by percentage so text never distorts.
 */
import { pct, type Tick } from "@/components/charts/scale";

/** Horizontal hairline grid with the y labels outside the plot on the left (one y axis only). */
export function YGrid({
  ticks,
  y,
  labelWidth,
}: {
  ticks: Tick[];
  /** Value → percent from the top. */
  y: (v: number) => number;
  labelWidth: number;
}) {
  return (
    <div aria-hidden data-axis="y" className="pointer-events-none absolute inset-0">
      {ticks.map((t) => (
        <div key={t.value}>
          <div className="absolute inset-x-0 h-px bg-chart-grid" style={{ top: pct(y(t.value)) }} />
          <span
            className="absolute -translate-y-1/2 pr-2 text-right text-[11px] text-muted-foreground tabular-nums"
            style={{ top: pct(y(t.value)), left: -labelWidth, width: labelWidth }}
          >
            {t.label}
          </span>
        </div>
      ))}
    </div>
  );
}

/** X labels under the plot, centred on their positions. */
export function XLabels({
  ticks,
  x,
  marginLeft,
  marginRight = 0,
}: {
  ticks: Tick[];
  x: (v: number) => number;
  marginLeft: number;
  marginRight?: number;
}) {
  return (
    <div
      aria-hidden
      data-axis="x"
      className="relative mt-1.5 h-[18px]"
      style={{ marginLeft, marginRight }}
    >
      {ticks.map((t) => (
        <span
          key={t.value}
          className="absolute -translate-x-1/2 text-[11px] whitespace-nowrap text-muted-foreground tabular-nums"
          style={{ left: pct(x(t.value)) }}
        >
          {t.label}
        </span>
      ))}
    </div>
  );
}
