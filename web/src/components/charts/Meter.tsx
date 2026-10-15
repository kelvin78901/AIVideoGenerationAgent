import { cn } from "@/lib/utils";

export interface MeterSegment {
  key: string;
  value: number;
  /** CSS colour (a `var(--chart-*)` token). */
  color: string;
}

/**
 * Horizontal meter: segments laid end to end on a track that is a light step of the same ramp
 * (budget bar, KPI progress, VRAM). Neighbouring segments are separated by a 2px card gap.
 * Values past `max` are clipped to the track.
 */
export function Meter({
  segments,
  max,
  label,
  size = "md",
  className,
}: {
  segments: MeterSegment[];
  max: number;
  /** Accessible description; omit when the numbers are already written next to the meter. */
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const starts = segments.map((_, i) => segments.slice(0, i).reduce((n, s) => n + s.value, 0));
  const at = (v: number) => Math.min(100, (v / max) * 100);
  return (
    <div
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-meter
      className={cn(
        "relative overflow-hidden bg-chart-track",
        size === "lg" && "h-3.5 rounded-[7px]",
        size === "md" && "h-2.5 rounded-[5px]",
        size === "sm" && "h-1.5 rounded-[3px]",
        className,
      )}
    >
      {segments.map((s, i) => {
        const from = at(starts[i] ?? 0);
        const to = at((starts[i] ?? 0) + s.value);
        return (
          <div
            key={s.key}
            data-segment={s.key}
            className={cn("absolute inset-y-0", i > 0 && "border-l-2 border-card")}
            style={{ left: `${from}%`, width: `${to - from}%`, background: s.color }}
          />
        );
      })}
    </div>
  );
}
