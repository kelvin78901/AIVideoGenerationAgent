import { cn } from "@/lib/utils";

export interface HBarSegment {
  key: string;
  value: number;
  /** CSS colour (a `var(--chart-*)` token). */
  color: string;
}

/**
 * One horizontal bar of a bar list (shot stages, components, API cost, QA issues): segments left
 * to right on a shared `max`, square at the baseline, 4px rounded data-end, 2px gaps between
 * segments. No track: the empty part is air. Thickness stays ≤ 24px (SPEC 11.3).
 */
export function HBar({
  segments,
  max,
  thickness = 16,
  label,
  minWidth = 0,
  className,
}: {
  segments: HBarSegment[];
  max: number;
  thickness?: number;
  /** Accessible description of the whole bar; omit when the row already says it in text. */
  label?: string;
  /** Smallest visible width in percent, so a $0.01 bar still shows (prototype 0.6 %). */
  minWidth?: number;
  className?: string;
}) {
  const segs = segments.filter((s) => s.value > 0);
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-hbar
      className={cn("flex min-w-0 items-center gap-0.5", className)}
      style={{ height: Math.max(thickness, 1) + 2 }}
    >
      {segs.map((s, i) => (
        <span
          key={s.key}
          data-segment={s.key}
          className={cn("block shrink-0", i === segs.length - 1 && "rounded-r")}
          style={{
            height: thickness,
            width: `max(calc(${((s.value / max) * 100).toFixed(2)}% - 2px), ${minWidth}%)`,
            background: s.color,
          }}
        />
      ))}
    </span>
  );
}
