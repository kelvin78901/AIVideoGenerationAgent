import { useTranslation } from "react-i18next";

import type { Asset, CandidatesPayload, TextSettings } from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { CandidateGrid } from "@/components/CandidateGrid";
import { cn } from "@/lib/utils";

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
 * compositing shows the text laid over it, as post will paste it (M7). */
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
  const ocrLine = useOcrLine();
  const text = asset.text;
  const method = madeWith?.method ?? text?.method ?? "composite";
  const cards = candidates.map((c, i) => {
    const ocr = text ? ocrLine(c, method) : null;
    return {
      label: t("cands.label", { n: versionNo, letter: LETTERS[i] }),
      letter: LETTERS[i] ?? "",
      seed: `${asset.id}-${versionNo}-${i}`,
      src: srcs[i] ?? null,
      tile: text ? (
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
      ) : undefined,
      overlay:
        text && method === "composite" ? (
          <div
            className={cn(
              "absolute inset-x-3 top-1/2 -translate-y-1/2 rounded px-2 py-1.5 text-center text-sm leading-relaxed shadow-md",
              TEXT_TILE[text.style],
            )}
          >
            {text.exact}
          </div>
        ) : undefined,
      meta: (
        <>
          <span className="text-xs text-muted-foreground">
            {text
              ? t(method === "composite" ? "cands.metaComposite" : "cands.metaModel")
              : asset.kind === "character"
                ? t("cands.metaCharacter")
                : t("cands.metaOther", { aspect })}
          </span>
          {ocr ? <span className={cn("text-xs", OCR_TONE[ocr.tone])}>{ocr.text}</span> : null}
        </>
      ),
    };
  });
  return (
    <CandidateGrid
      label={t("cands.title")}
      cards={cards}
      aspect={aspect}
      picked={asset.pick}
      pickedText={t("cands.picked")}
      disabled={locked}
      onPick={onPick}
    />
  );
}
