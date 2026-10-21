import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The clip playing now, page-wide: starting another one pauses it. */
let playingNow: HTMLAudioElement | null = null;

/**
 * One audio clip (M3: voice samples, dubbed lines): play / pause, the waveform the backend
 * measured (bars light up as it plays) and the duration. Only one clip plays at a time.
 */
export function AudioPlayer({
  src,
  waveform,
  duration,
  label,
  className,
}: {
  src: string;
  /** 0–1 peaks (`media/audio.py`); none = a plain progress bar. */
  waveform?: number[] | null;
  duration?: number | null;
  /** What is playing, for the button's accessible name. */
  label: string;
  className?: string;
}) {
  const { t } = useTranslation("components");
  const ref = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  // A new file (or leaving the page) stops the old one.
  useEffect(() => {
    return () => {
      const a = ref.current;
      if (!a) return;
      a.pause();
      if (playingNow === a) playingNow = null;
      ref.current = null;
    };
  }, [src]);

  function audio(): HTMLAudioElement {
    if (ref.current) return ref.current;
    const a = new Audio(src);
    a.addEventListener("play", () => setPlaying(true));
    a.addEventListener("pause", () => setPlaying(false));
    a.addEventListener("timeupdate", () => {
      setProgress(a.duration ? a.currentTime / a.duration : 0);
    });
    a.addEventListener("ended", () => {
      setPlaying(false);
      setProgress(0);
    });
    ref.current = a;
    return a;
  }

  async function toggle() {
    const a = audio();
    if (playing) {
      a.pause();
      return;
    }
    if (playingNow && playingNow !== a) playingNow.pause();
    playingNow = a;
    try {
      await a.play();
    } catch {
      setPlaying(false);
    }
  }

  const bars = waveform?.length ? waveform : null;
  const lit = Math.round(progress * (bars?.length ?? 0));
  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)}>
      <Button
        type="button"
        size="icon"
        variant="outline"
        aria-label={t(playing ? "audio.pause" : "audio.play", { label })}
        aria-pressed={playing}
        onClick={() => void toggle()}
      >
        {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
      </Button>
      {bars ? (
        <div aria-hidden className="flex h-8 min-w-0 flex-1 items-center gap-0.5 overflow-hidden">
          {bars.map((h, i) => (
            <span
              key={i}
              className={cn(
                "w-1 shrink-0 rounded-full",
                playing && i < lit ? "bg-primary" : "bg-muted-foreground/40",
              )}
              style={{ height: `${Math.max(12, h * 100)}%` }}
            />
          ))}
        </div>
      ) : (
        <div aria-hidden className="h-1 min-w-0 flex-1 rounded-full bg-muted">
          <div className="h-1 rounded-full bg-primary" style={{ width: `${progress * 100}%` }} />
        </div>
      )}
      {duration != null ? (
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {t("audio.seconds", { s: duration.toFixed(1) })}
        </span>
      ) : null}
    </div>
  );
}
