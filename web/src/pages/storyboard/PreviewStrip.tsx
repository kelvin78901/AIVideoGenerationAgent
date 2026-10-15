import { Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Shot } from "@/api/schemas/shots";
import type { Aspect } from "@/api/schemas/spec";
import { MediaThumb } from "@/components/MediaThumb";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** How long each shot stays up while the preview plays (prototype: 0.7 s). */
const PREVIEW_STEP_MS = 700;

/**
 * 预演: the current frame and a strip with one block per shot, as wide as its duration.
 * Playing walks through the shots; clicking a block selects that shot.
 */
export function PreviewStrip({
  shots,
  aspect,
  selectedId,
  onSelect,
}: {
  shots: Shot[];
  aspect: Aspect;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation("storyboard");
  const [playIdx, setPlayIdx] = useState<number | null>(null);
  const total = shots.reduce((n, s) => n + s.duration_s, 0);

  useEffect(() => {
    if (playIdx === null) return;
    const id = setTimeout(
      () => setPlayIdx(playIdx >= shots.length - 1 ? null : playIdx + 1),
      PREVIEW_STEP_MS,
    );
    return () => clearTimeout(id);
  }, [playIdx, shots.length]);

  const current =
    (playIdx !== null ? shots[playIdx] : undefined) ??
    shots.find((s) => s.id === selectedId) ??
    shots[0];

  return (
    <section
      aria-label={t("preview.label")}
      className="flex flex-wrap items-center gap-4 rounded-lg border bg-card p-3"
    >
      <div className="w-20 shrink-0">
        {current ? (
          <MediaThumb
            aspect={aspect}
            seed={current.label}
            label={current.label}
            caption={<span data-testid="preview-caption">{current.summary}</span>}
          />
        ) : null}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            aria-pressed={playIdx !== null}
            onClick={() => setPlayIdx(playIdx === null ? 0 : null)}
          >
            {playIdx === null ? <Play aria-hidden /> : <Pause aria-hidden />}
            {t(playIdx === null ? "preview.play" : "preview.pause")}
          </Button>
          <span className="text-xs text-muted-foreground">
            {t("preview.total", { seconds: total })}
          </span>
        </div>
        <div className="flex gap-1">
          {shots.map((s, i) => {
            const on = playIdx !== null ? i === playIdx : s.id === selectedId;
            return (
              <button
                key={s.id}
                type="button"
                aria-label={t("preview.shot", { id: s.label, seconds: s.duration_s })}
                aria-current={on ? "true" : undefined}
                onClick={() => {
                  setPlayIdx(null);
                  onSelect(s.id);
                }}
                style={{ flex: `${s.duration_s} 1 0` }}
                className={cn(
                  "flex min-w-0 flex-col items-start rounded-sm border px-1.5 py-1 text-left font-mono text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  on
                    ? "border-primary bg-tone-info-bg text-tone-info-fg"
                    : "border-transparent bg-media text-media-foreground",
                )}
              >
                <span className="truncate">{s.label}</span>
                <span className="opacity-70">{t("preview.seconds", { n: s.duration_s })}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
