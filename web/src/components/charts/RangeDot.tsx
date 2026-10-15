import { pct } from "@/components/charts/scale";

/**
 * Range-and-dot row: a hairline baseline, a 2px line from `min` to `max` and an 8px+ dot at the
 * median with a 2px card ring. Positions are percentages of `[0, domainMax]`.
 */
export function RangeDot({
  min,
  max,
  median,
  domainMax,
  label,
}: {
  min: number;
  max: number;
  median: number;
  domainMax: number;
  label: string;
}) {
  const x = (v: number) => Math.min(100, Math.max(0, (v / domainMax) * 100));
  return (
    <span role="img" aria-label={label} data-range-dot className="relative block h-7">
      <span className="absolute inset-x-0 top-1/2 h-px bg-chart-grid" />
      <span
        data-range
        className="absolute top-1/2 -mt-px h-0.5 rounded-full bg-chart-crosshair"
        style={{ left: pct(x(min)), width: pct(Math.max(x(max) - x(min), 0.5)) }}
      />
      <span
        data-dot
        className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-chart-1 ring-2 ring-card"
        style={{ left: pct(x(median)) }}
      />
    </span>
  );
}
