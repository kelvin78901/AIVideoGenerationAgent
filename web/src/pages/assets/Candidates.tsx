import { Check, Pause, Play, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { Asset, CandidatesPayload } from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { MediaThumb } from "@/components/MediaThumb";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const LETTERS = "ABCD";

/** Paper / screen colours of on-screen text tiles: they depict the medium, not UI chrome. */
const TEXT_TILE: Record<NonNullable<Asset["text"]>["style"], string> = {
  handwritten: "bg-[#EFE2A6] text-[#2B2412] font-serif",
  printed: "bg-[#F4F3EF] text-[#1A1B1E]",
  screen: "bg-[#26282C] text-[#F2F2EF] font-sans",
};

type Candidate = CandidatesPayload["candidates"][number];

/** 候选: 4 reference images, or 4 on-screen text images with their OCR check. */
export function ImageCandidates({
  asset,
  versionNo,
  candidates,
  aspect,
  locked,
  onPick,
}: {
  asset: Asset;
  versionNo: number;
  candidates: Candidate[];
  aspect: Aspect;
  locked: boolean;
  onPick: (i: number) => void;
}) {
  const { t } = useTranslation("assets");
  const text = asset.text;
  return (
    <div
      role="radiogroup"
      aria-label={t("cands.title")}
      className="grid grid-cols-2 gap-3 sm:grid-cols-4"
    >
      {candidates.map((c, i) => {
        const on = asset.pick === i;
        const label = t("cands.label", { n: versionNo, letter: LETTERS[i] });
        const ocrOk = !text || text.method === "composite" || c.ocr === text.exact;
        const ocr = !text
          ? null
          : ocrOk
            ? t("cands.ocrOk")
            : (c.ocr ?? "").length < text.exact.length
              ? t("cands.ocrMissing")
              : t("cands.ocrWrong");
        return (
          <button
            key={i}
            type="button"
            role="radio"
            aria-checked={on}
            aria-label={label}
            disabled={locked}
            onClick={() => onPick(i)}
            className={cn(
              "flex flex-col gap-1.5 rounded-lg border-2 p-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default",
              on ? "border-primary" : "border-transparent hover:border-border",
            )}
          >
            <div className="relative">
              {text ? (
                <div
                  className={cn(
                    "flex aspect-square items-center justify-center rounded-md p-3 text-center text-sm leading-relaxed",
                    TEXT_TILE[text.style],
                  )}
                >
                  {text.method === "composite"
                    ? t("cands.compositeSample", { text: text.exact })
                    : (c.ocr ?? "")}
                </div>
              ) : (
                <MediaThumb
                  aspect={aspect}
                  seed={`${asset.id}-${versionNo}-${i}`}
                  label={LETTERS[i]}
                />
              )}
              {on ? (
                <StatusBadge tone="info" icon={Check} className="absolute top-1.5 right-1.5">
                  {t("cands.picked")}
                </StatusBadge>
              ) : null}
            </div>
            <span className="text-xs font-medium">{label}</span>
            <span className="text-xs text-muted-foreground">
              {text
                ? t(text.method === "composite" ? "cands.metaComposite" : "cands.metaModel")
                : asset.kind === "character"
                  ? t("cands.metaCharacter")
                  : t("cands.metaOther", { aspect })}
            </span>
            {ocr ? (
              <span className={cn("text-xs", ocrOk ? "text-tone-info-fg" : "text-tone-warn-fg")}>
                {ocr}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

/** 音色候选: static waveforms with a play toggle, a pick, and auditions with script lines. */
export function VoiceCandidates({
  asset,
  versionNo,
  candidates,
  locked,
  onPick,
}: {
  asset: Asset;
  versionNo: number;
  candidates: Candidate[];
  locked: boolean;
  onPick: (i: number) => void;
}) {
  const { t } = useTranslation("assets");
  const [playing, setPlaying] = useState<number | null>(null);

  // A demo clip "plays" for 2.5 s (no audio files until M3).
  useEffect(() => {
    if (playing === null) return;
    const id = setTimeout(() => setPlaying(null), 2500);
    return () => clearTimeout(id);
  }, [playing]);

  return (
    <div className="flex flex-col gap-3">
      <div role="radiogroup" aria-label={t("voice.cands")} className="flex flex-col gap-2">
        {candidates.map((c, i) => {
          const on = asset.pick === i;
          const isPlaying = playing === i;
          const letter = LETTERS[i] ?? "";
          return (
            <div
              key={i}
              className={cn(
                "flex items-center gap-3 rounded-lg border px-3 py-2",
                on && "border-primary bg-tone-info-bg/40",
              )}
            >
              <Button
                size="icon"
                variant="outline"
                aria-label={t(isPlaying ? "voice.pause" : "voice.play", { letter })}
                aria-pressed={isPlaying}
                onClick={() => setPlaying(isPlaying ? null : i)}
              >
                {isPlaying ? <Pause aria-hidden /> : <Play aria-hidden />}
              </Button>
              <div aria-hidden className="flex h-8 items-center gap-0.5">
                {(c.waveform ?? []).map((h, j) => (
                  <span
                    key={j}
                    className={cn(
                      "w-1 rounded-full",
                      isPlaying ? "bg-primary" : "bg-muted-foreground/40",
                    )}
                    style={{ height: `${Math.max(12, h * 100)}%` }}
                  />
                ))}
              </div>
              <span className="flex-1 text-sm">
                {t("voice.label", { n: versionNo, letter, label: c.label ?? "" })}
              </span>
              <Button
                size="sm"
                role="radio"
                aria-checked={on}
                variant={on ? "default" : "outline"}
                disabled={locked}
                onClick={() => onPick(i)}
              >
                {t(on ? "voice.picked" : "voice.pick")}
              </Button>
            </div>
          );
        })}
      </div>
      {asset.voice?.lines.length ? (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs font-medium">{t("voice.lines")}</div>
          {asset.voice.lines.map((l) => (
            <div key={l.text} className="flex items-center gap-2 text-sm">
              <Button
                size="icon"
                variant="ghost"
                aria-label={t("voice.tryLine", { text: l.text })}
                onClick={() => toast.info(t("voice.trying", { text: l.text, tone: l.tone }))}
              >
                <Volume2 aria-hidden />
              </Button>
              <span>{l.text}</span>
              <span className="text-xs text-muted-foreground">{l.tone}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
