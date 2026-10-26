import { Check, Maximize2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { Aspect } from "@/api/schemas/spec";
import { MediaLightbox } from "@/components/MediaLightbox";
import { MediaThumb } from "@/components/MediaThumb";
import { StatusBadge } from "@/components/StatusBadge";
import { CARD_INSET, CARD_WIDTH } from "@/lib/cards";
import { cn } from "@/lib/utils";

/** One picture to choose from. */
export interface CandidateCard {
  /** 「v1 · A」: the radio's name, under the picture. */
  label: string;
  /** Big letter of the stand-in frame while there is no picture. */
  letter: string;
  /** Stand-in hue (`MediaThumb`). */
  seed: string;
  src: string | null;
  /** Shown instead of the picture when there is none (an on-screen text tile). */
  tile?: ReactNode;
  /** Laid over the picture (text pasted in post). */
  overlay?: ReactNode;
  /** Lines under the label. */
  meta?: ReactNode;
}

/**
 * 候选 (assets, keyframes): small cards of one size on any screen, one picked (a radio group);
 * 「放大」 on a picture opens it at screen size, ← → the others.
 */
export function CandidateGrid({
  label,
  cards,
  aspect,
  picked,
  pickedText,
  disabled,
  onPick,
}: {
  /** The radio group's name. */
  label: string;
  cards: CandidateCard[];
  aspect: Aspect;
  picked: number;
  /** The badge on the picked card (「已选」). */
  pickedText: string;
  /** Nothing can be picked (locked, confirmed). */
  disabled: boolean;
  onPick: (i: number) => void;
}) {
  const { t } = useTranslation("components");
  const [zoomed, setZoomed] = useState<number | null>(null);
  // The pictures there are, in order, for the lightbox's ← →.
  const pictures = cards.flatMap((c, i) => (c.src ? [{ src: c.src, label: c.label, i }] : []));
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-3">
      {cards.map((c, i) => {
        const on = picked === i;
        return (
          <div key={i} className="relative shrink-0" style={{ width: CARD_WIDTH[aspect] }}>
            <button
              type="button"
              role="radio"
              aria-checked={on}
              aria-label={c.label}
              disabled={disabled}
              onClick={() => onPick(i)}
              className={cn(
                "flex w-full flex-col gap-1.5 rounded-lg border-2 p-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default",
                on ? "border-primary" : "border-transparent hover:border-border",
              )}
            >
              <div className="relative">
                {c.tile && !c.src ? (
                  c.tile
                ) : (
                  <MediaThumb
                    aspect={aspect}
                    seed={c.seed}
                    src={c.src}
                    alt={c.label}
                    label={c.letter}
                    overlay={c.overlay}
                  />
                )}
                {on ? (
                  <StatusBadge tone="info" icon={Check} className="absolute top-1.5 right-1.5">
                    {pickedText}
                  </StatusBadge>
                ) : null}
              </div>
              <span className="text-xs font-medium">{c.label}</span>
              {c.meta}
            </button>
            {c.src ? (
              // Over the picture, beside the card (a control inside a radio would be hidden).
              <div
                className="pointer-events-none absolute"
                style={{
                  top: CARD_INSET,
                  left: CARD_INSET,
                  width: `calc(100% - ${2 * CARD_INSET}px)`,
                  aspectRatio: aspect.replace(":", " / "),
                }}
              >
                <button
                  type="button"
                  aria-label={t("lightbox.zoom", { label: c.label })}
                  title={t("lightbox.zoom", { label: c.label })}
                  onClick={() => setZoomed(pictures.findIndex((p) => p.i === i))}
                  className="pointer-events-auto absolute right-1.5 bottom-1.5 flex size-7 items-center justify-center rounded-md bg-black/45 text-white outline-none hover:bg-black/65 focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Maximize2 className="size-3.5" aria-hidden />
                </button>
              </div>
            ) : null}
          </div>
        );
      })}
      <MediaLightbox items={pictures} index={zoomed} onIndex={setZoomed} />
    </div>
  );
}
