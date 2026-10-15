import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";

import type { BlockingItem, Framing } from "@/api/schemas/shots";
import { cn } from "@/lib/utils";

const clamp = (v: number) => Math.min(1, Math.max(0, v));
const STEP = 0.02;
const KEYS: Record<string, [number, number]> = {
  ArrowLeft: [-STEP, 0],
  ArrowRight: [STEP, 0],
  ArrowUp: [0, -STEP],
  ArrowDown: [0, STEP],
};

/**
 * 站位（俯视）: people, props and the camera on a top-down plan. Drag with the pointer, or
 * focus an item and use the arrow keys; `onChange` gets the whole layout once a move ends.
 */
export function Blocking({
  items,
  framing,
  onChange,
}: {
  items: BlockingItem[];
  framing: Framing;
  onChange: (items: BlockingItem[]) => void;
}) {
  const { t } = useTranslation("storyboard");
  const { t: te } = useTranslation("enums");
  const plane = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ id: string; x: number; y: number } | null>(null);

  const shown = items.map((it) => (drag?.id === it.id ? { ...it, x: drag.x, y: drag.y } : it));
  const labelOf = (it: BlockingItem) =>
    it.kind === "camera" ? t("shot.camera", { framing: te(`framing.${framing}`) }) : it.label;
  const commit = (id: string, x: number, y: number) =>
    onChange(items.map((it) => (it.id === id ? { ...it, x, y } : it)));

  const pointAt = (e: PointerEvent) => {
    const r = plane.current?.getBoundingClientRect();
    if (!r || !r.width || !r.height) return null;
    return { x: clamp((e.clientX - r.left) / r.width), y: clamp((e.clientY - r.top) / r.height) };
  };

  const onKey = (it: BlockingItem, e: KeyboardEvent) => {
    const d = KEYS[e.key];
    if (!d) return;
    e.preventDefault();
    commit(it.id, clamp(it.x + d[0]), clamp(it.y + d[1]));
  };

  return (
    <div
      ref={plane}
      role="group"
      aria-label={t("shot.blocking")}
      className="relative aspect-[4/3] w-full touch-none overflow-hidden rounded-md border bg-muted/50 [background-image:radial-gradient(var(--border)_1px,transparent_1px)] [background-size:16px_16px]"
    >
      {shown.map((it) => (
        <button
          key={it.id}
          type="button"
          aria-label={t("shot.blockingItem", {
            label: labelOf(it),
            x: Math.round(it.x * 100),
            y: Math.round(it.y * 100),
          })}
          onKeyDown={(e) => onKey(it, e)}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture?.(e.pointerId);
            setDrag({ id: it.id, x: it.x, y: it.y });
          }}
          onPointerMove={(e) => {
            if (drag?.id !== it.id) return;
            const p = pointAt(e);
            if (p) setDrag({ id: it.id, ...p });
          }}
          onPointerUp={() => {
            if (drag?.id === it.id && (drag.x !== it.x || drag.y !== it.y))
              commit(it.id, drag.x, drag.y);
            setDrag(null);
          }}
          style={{ left: `${it.x * 100}%`, top: `${it.y * 100}%` }}
          className={cn(
            "absolute -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-full border px-2 py-0.5 text-xs whitespace-nowrap shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing",
            it.kind === "character" && "border-primary bg-primary text-primary-foreground",
            it.kind === "camera" && "border-foreground bg-foreground text-background",
            it.kind === "prop" && "border-tone-warn-border bg-card text-tone-warn-fg",
            it.kind === "landmark" && "bg-card",
          )}
        >
          {labelOf(it)}
        </button>
      ))}
    </div>
  );
}
