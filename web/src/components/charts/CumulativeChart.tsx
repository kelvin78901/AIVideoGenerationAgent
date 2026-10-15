import { area, line } from "d3-shape";

import { XLabels, YGrid } from "@/components/charts/axis";
import { percentScale, pct, type Tick } from "@/components/charts/scale";

export interface Point {
  x: number;
  y: number;
}

/** A hover band (one bucket): the strip from `x0` to `x1`, its readout point and accessible name. */
export interface Strip {
  x0: number;
  x1: number;
  point: Point;
  label: string;
}

const VB_W = 1000;
const VB_H = 300;

/**
 * Cumulative line + 10 % area wash up to "now", a dashed projection from now to the end of the
 * axis, an optional budget rule, and a crosshair that snaps to the hovered bucket (SPEC 11.3).
 * Hover state is owned by the caller so another chart can share it.
 */
export function CumulativeChart({
  xDomain,
  yMax,
  xTicks,
  yTicks,
  points,
  now,
  projection,
  budget,
  strips,
  hover,
  onHover,
  height = 230,
  marginLeft = 40,
  marginRight = 56,
}: {
  xDomain: [number, number];
  yMax: number;
  xTicks: Tick[];
  yTicks: Tick[];
  /** Cumulative points in x order; the last one is "now". */
  points: Point[];
  now: Point & { label: string };
  projection?: Point & { label: string };
  budget?: { y: number; label: string };
  strips: Strip[];
  hover: number | null;
  onHover: (i: number | null) => void;
  height?: number;
  marginLeft?: number;
  marginRight?: number;
}) {
  const x = percentScale(xDomain);
  const y = percentScale([0, yMax], true);
  // Path coordinates live in a stretched 1000×300 viewBox; strokes stay 2px (non-scaling).
  const vx = (p: Point) => (x(p.x) / 100) * VB_W;
  const vy = (p: Point) => (y(p.y) / 100) * VB_H;
  const linePath = line<Point>().x(vx).y(vy)(points) ?? "";
  const areaPath = area<Point>().x(vx).y0(VB_H).y1(vy)(points) ?? "";
  const hovered = hover != null ? strips[hover] : undefined;

  return (
    <div>
      <div
        className="relative"
        style={{ height, margin: `10px ${marginRight}px 0 ${marginLeft}px` }}
      >
        <YGrid ticks={yTicks} y={y} labelWidth={marginLeft} />
        {budget ? (
          <div aria-hidden data-budget>
            <div
              className="absolute inset-x-0 border-t border-chart-crosshair/70"
              style={{ top: pct(y(budget.y)) }}
            />
            <span
              className="absolute -translate-y-1/2 pl-1 text-[11px] whitespace-nowrap text-muted-foreground"
              style={{ top: pct(y(budget.y)), left: "100%" }}
            >
              {budget.label}
            </span>
          </div>
        ) : null}
        <svg
          aria-hidden
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          preserveAspectRatio="none"
          className="absolute inset-0 size-full overflow-visible"
        >
          <path d={areaPath} className="fill-chart-1/10" />
          {projection ? (
            <path
              data-projection
              d={`M ${vx(now)} ${vy(now)} L ${vx(projection)} ${vy(projection)}`}
              fill="none"
              className="stroke-chart-1"
              strokeOpacity={0.6}
              strokeWidth={2}
              strokeDasharray="5 5"
              vectorEffect="non-scaling-stroke"
            />
          ) : null}
          <path
            data-line
            d={linePath}
            fill="none"
            className="stroke-chart-1"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {hovered ? (
          <>
            <div
              aria-hidden
              data-crosshair
              className="absolute inset-y-0 w-px bg-chart-crosshair"
              style={{ left: pct(x(hovered.point.x)) }}
            />
            <Dot left={x(hovered.point.x)} top={y(hovered.point.y)} />
          </>
        ) : null}
        <Dot left={x(now.x)} top={y(now.y)} />
        <span
          aria-hidden
          className="absolute translate-x-2 translate-y-1 text-xs font-medium whitespace-nowrap"
          style={{ left: pct(x(now.x)), top: pct(y(now.y)) }}
        >
          {now.label}
        </span>
        {projection ? (
          <span
            aria-hidden
            className="absolute right-0 -translate-y-[130%] text-xs whitespace-nowrap text-muted-foreground"
            style={{ top: pct(y(projection.y)) }}
          >
            {projection.label}
          </span>
        ) : null}
        {strips.map((s, i) => (
          <button
            key={s.x0}
            type="button"
            aria-label={s.label}
            aria-pressed={hover === i}
            onPointerEnter={() => onHover(i)}
            onFocus={() => onHover(i)}
            onClick={() => onHover(i)}
            className="absolute inset-y-0 p-0 outline-none focus-visible:bg-accent/40"
            style={{ left: pct(x(s.x0)), width: pct(x(s.x1) - x(s.x0)) }}
          />
        ))}
      </div>
      <XLabels ticks={xTicks} x={x} marginLeft={marginLeft} marginRight={marginRight} />
    </div>
  );
}

/** ≥ 8px marker with a 2px ring in the card colour. */
function Dot({ left, top }: { left: number; top: number }) {
  return (
    <div
      aria-hidden
      data-dot
      className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-chart-1 ring-2 ring-card"
      style={{ left: pct(left), top: pct(top) }}
    />
  );
}
