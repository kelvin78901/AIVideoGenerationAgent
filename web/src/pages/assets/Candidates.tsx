import { Check, Maximize2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Asset, CandidatesPayload, TextSettings } from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { MediaLightbox } from "@/components/MediaLightbox";
import { MediaThumb } from "@/components/MediaThumb";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";
import { CARD_INSET, CARD_WIDTH } from "@/pages/assets/status";

const LETTERS = "ABCD";

/** Paper / screen colours of on-screen text tiles: they depict the medium, not UI chrome. */
const TEXT_TILE: Record<TextSettings["style"], string> = {
  handwritten: "bg-[#EFE2A6] text-[#2B2412] font-serif",
  printed: "bg-[#F4F3EF] text-[#1A1B1E]",
  screen: "bg-[#26282C] text-[#F2F2EF] font-sans",
};

type Candidate = CandidatesPayload["candidates"][number];
type Tone = "ok" | "bad" | "none";
const OCR_TONE: Record<Tone, string> = {
  ok: "text-tone-info-fg",
  bad: "text-tone-warn-fg",
  none: "text-muted-foreground",
};

/** What the backend's OCR check says about a text candidate (`ocr_ok`, `ocr_issue`). */
function useOcrLine() {
  const { t } = useTranslation("assets");
  return (c: Candidate, method: TextSettings["method"]): { text: string; tone: Tone } => {
    if (c.ocr_ok === true)
      return { text: t(method === "composite" ? "cands.ocrBlank" : "cands.ocrOk"), tone: "ok" };
    if (c.ocr_ok === false) {
      const text =
        c.ocr_issue === "has_text"
          ? t("cands.ocrHasText", { read: c.ocr ?? "" })
          : c.ocr_issue === "missing"
            ? t("cands.ocrMissing")
            : t("cands.ocrWrong");
      return { text, tone: "bad" };
    }
    return { text: t("cands.ocrUnchecked"), tone: "none" };
  };
}

/** 候选: 4 reference images, or 4 on-screen text images with their OCR check. A base for
 * compositing shows the text laid over it, as post will paste it (M7). The cards are small;
 * 「放大」 on a picture opens it at screen size. */
export function ImageCandidates({
  asset,
  versionNo,
  candidates,
  srcs,
  aspect,
  madeWith,
  locked,
  onPick,
}: {
  asset: Asset;
  versionNo: number;
  candidates: Candidate[];
  /** Each candidate's picture (`files[]` with its `idx`), when the version has files. */
  srcs: (string | null)[];
  aspect: Aspect;
  /** On-screen text: the settings the version was made with (`payload.text`). */
  madeWith?: TextSettings | null;
  locked: boolean;
  onPick: (i: number) => void;
}) {
  const { t } = useTranslation("assets");
  const { t: tc } = useTranslation("components");
  const ocrLine = useOcrLine();
  const [zoomed, setZoomed] = useState<number | null>(null);
  const text = asset.text;
  const method = madeWith?.method ?? text?.method ?? "composite";
  const label = (i: number) => t("cands.label", { n: versionNo, letter: LETTERS[i] });
  // The pictures there are, in order, for the lightbox's ← →.
  const pictures = srcs.flatMap((src, i) => (src ? [{ src, label: label(i), i }] : []));
  return (
    <div role="radiogroup" aria-label={t("cands.title")} className="flex flex-wrap gap-3">
      {candidates.map((c, i) => {
        const on = asset.pick === i;
        const ocr = text ? ocrLine(c, method) : null;
        const src = srcs[i];
        return (
          <div key={i} className="relative shrink-0" style={{ width: CARD_WIDTH[aspect] }}>
            <button
              type="button"
              role="radio"
              aria-checked={on}
              aria-label={label(i)}
              disabled={locked}
              onClick={() => onPick(i)}
              className={cn(
                "flex w-full flex-col gap-1.5 rounded-lg border-2 p-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default",
                on ? "border-primary" : "border-transparent hover:border-border",
              )}
            >
              <div className="relative">
                {text && !src ? (
                  <div
                    className={cn(
                      "flex aspect-square items-center justify-center rounded-md p-3 text-center text-sm leading-relaxed",
                      TEXT_TILE[text.style],
                    )}
                  >
                    {method === "composite"
                      ? t("cands.compositeSample", { text: text.exact })
                      : (c.ocr ?? "")}
                  </div>
                ) : (
                  <MediaThumb
                    aspect={aspect}
                    seed={`${asset.id}-${versionNo}-${i}`}
                    src={src}
                    alt={label(i)}
                    label={LETTERS[i]}
                    overlay={
                      text && method === "composite" ? (
                        <div
                          className={cn(
                            "absolute inset-x-3 top-1/2 -translate-y-1/2 rounded px-2 py-1.5 text-center text-sm leading-relaxed shadow-md",
                            TEXT_TILE[text.style],
                          )}
                        >
                          {text.exact}
                        </div>
                      ) : null
                    }
                  />
                )}
                {on ? (
                  <StatusBadge tone="info" icon={Check} className="absolute top-1.5 right-1.5">
                    {t("cands.picked")}
                  </StatusBadge>
                ) : null}
              </div>
              <span className="text-xs font-medium">{label(i)}</span>
              <span className="text-xs text-muted-foreground">
                {text
                  ? t(method === "composite" ? "cands.metaComposite" : "cands.metaModel")
                  : asset.kind === "character"
                    ? t("cands.metaCharacter")
                    : t("cands.metaOther", { aspect })}
              </span>
              {ocr ? <span className={cn("text-xs", OCR_TONE[ocr.tone])}>{ocr.text}</span> : null}
            </button>
            {src ? (
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
                  aria-label={tc("lightbox.zoom", { label: label(i) })}
                  title={tc("lightbox.zoom", { label: label(i) })}
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
