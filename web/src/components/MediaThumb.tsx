import type { ReactNode } from "react";

import type { Aspect } from "@/api/schemas/spec";
import { cn } from "@/lib/utils";

const ratio: Record<Aspect, string> = {
  "9:16": "9 / 16",
  "16:9": "16 / 9",
  "3:4": "3 / 4",
  "1:1": "1 / 1",
  "21:9": "21 / 9",
};

/** Stable hue from a seed string, so the same shot or asset always gets the same frame. */
function hue(seed: string): number {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

/**
 * A media frame in the output-spec aspect (SPEC 16.4: portrait by default, landscape when the
 * spec says so). Shows `src` when there is a real file; until then a tinted placeholder with
 * the item's label, so pages lay out exactly as they will with real keyframes and takes.
 */
export function MediaThumb({
  aspect,
  seed,
  src,
  alt = "",
  label,
  caption,
  overlay,
  dashed = false,
  className,
}: {
  aspect: Aspect;
  seed: string;
  src?: string | null;
  alt?: string;
  /** Big text in the frame (shot id, take label). */
  label?: ReactNode;
  /** Small text at the bottom (description, duration). */
  caption?: ReactNode;
  /** Corner badges, play buttons, safe-area guides. */
  overlay?: ReactNode;
  /** Not generated yet / waiting: dashed outline instead of a filled frame. */
  dashed?: boolean;
  className?: string;
}) {
  const h = hue(seed);
  return (
    <div
      className={cn(
        "relative w-full overflow-hidden rounded-md text-media-foreground",
        dashed ? "border border-dashed border-media-muted bg-media/40" : "bg-media",
        className,
      )}
      style={{ aspectRatio: ratio[aspect] }}
    >
      {src ? (
        <img src={src} alt={alt} className="absolute inset-0 size-full object-cover" />
      ) : dashed ? null : (
        <div
          aria-hidden
          className="absolute inset-0 opacity-70"
          style={{
            background: `radial-gradient(120% 80% at 30% 20%, hsl(${h} 35% 34% / 0.9), transparent 60%), linear-gradient(160deg, hsl(${(h + 40) % 360} 25% 22%), hsl(${(h + 200) % 360} 20% 10%))`,
          }}
        />
      )}
      {label ? (
        <div className="absolute top-2 left-2 font-mono text-xs font-semibold drop-shadow">
          {label}
        </div>
      ) : null}
      {caption ? (
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-2 pt-6 pb-1.5 text-xs leading-snug">
          {caption}
        </div>
      ) : null}
      {overlay}
    </div>
  );
}
