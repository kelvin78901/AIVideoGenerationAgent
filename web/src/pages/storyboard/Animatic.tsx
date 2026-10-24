import { Pause, Play } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { fileUrl } from "@/api/client";
import type { Dub } from "@/api/schemas/dub";
import type { Shot } from "@/api/schemas/shots";
import type { Aspect, SafeArea } from "@/api/schemas/spec";
import { MediaThumb } from "@/components/MediaThumb";
import { SafeAreaOverlay } from "@/components/SafeAreaOverlay";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";
import { framePicture, frameSize, spanAt, timeline, type Cue } from "@/pages/storyboard/timeline";

/** Space plays / pauses unless the key belongs to what has focus. */
const OWNS_SPACE =
  "input, textarea, select, button, a, [contenteditable], [role=slider], [role=radio], [role=checkbox], [role=dialog], [role=alertdialog]";

/** The dubbed lines' audio, started and stopped with the clock (one element per line). */
function useCueAudio(cues: Cue[]) {
  const audios = useRef(new Map<string, HTMLAudioElement>());
  const on = useRef(new Set<string>());
  const stop = useCallback(() => {
    for (const id of on.current) audios.current.get(id)?.pause();
    on.current.clear();
  }, []);
  // New lines (a new take, an edit), or leaving the page: what plays stops.
  useEffect(() => {
    const all = audios.current;
    return () => {
      stop();
      all.clear();
    };
  }, [cues, stop]);
  const sync = useCallback(
    (t: number) => {
      for (const c of cues) {
        if (!c.src) continue;
        const inside = t >= c.start && t < c.end;
        if (inside && !on.current.has(c.lineId)) {
          let a = audios.current.get(c.lineId);
          if (!a) {
            a = new Audio(c.src);
            audios.current.set(c.lineId, a);
          }
          a.currentTime = t - c.start;
          on.current.add(c.lineId);
          a.play().catch(() => undefined);
        } else if (!inside && on.current.has(c.lineId)) {
          audios.current.get(c.lineId)?.pause();
          on.current.delete(c.lineId);
        }
      }
    },
    [cues],
  );
  return { sync, stop };
}

/**
 * 预演 (动态分镜, M4): the episode played on a clock, each shot as long as it runs, over its
 * picked keyframe (a continuous shot shows the keyframe of the shot it continues); the dubbed
 * lines play at their offsets under their subtitles, a line not dubbed yet is its subtitle
 * alone. 播放 starts from the top; 暂停 keeps the place and selects that shot; clicking the strip
 * jumps there; space plays and pauses. 安全区 lays the platform's UI over the frame and the
 * keyframe candidates.
 */
export function Animatic({
  shots,
  aspect,
  selectedId,
  onSelect,
  dub,
  area,
  showSafe,
  onShowSafe,
  dubPath,
}: {
  shots: Shot[];
  aspect: Aspect;
  selectedId: string;
  onSelect: (id: string) => void;
  dub: Dub | undefined;
  /** The spec's safe area (where subtitles sit, what the toggle shows); null until loaded. */
  area: SafeArea | null;
  showSafe: boolean;
  onShowSafe: (on: boolean) => void;
  /** 「去配音」: the assets page. */
  dubPath: string;
}) {
  const { t } = useTranslation("storyboard");
  const { spans, cues, total, missing } = useMemo(() => timeline(shots, dub), [shots, dub]);
  const [playing, setPlaying] = useState(false);
  // Where the clock is: null = at the top (nothing played yet, or played to the end).
  const [time, setTime] = useState<number | null>(null);
  const origin = useRef(0);
  // A jump while playing, for the next tick to take the clock to.
  const jump = useRef<number | null>(null);
  const { sync, stop } = useCueAudio(cues);

  const selected = spans.find((s) => s.shot.id === selectedId) ?? spans[0];
  // Paused, the clock stays with the shot it stopped in; picking another shot moves it there.
  const paused = time !== null ? spanAt(spans, time) : undefined;
  const at = playing ? (time ?? 0) : time !== null && paused?.shot.id === selectedId ? time : null;
  const span = at !== null ? spanAt(spans, at) : selected;
  const from = at ?? (time === null ? 0 : (selected?.start ?? 0));

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      if (jump.current !== null) {
        origin.current = performance.now() - jump.current * 1000;
        jump.current = null;
      }
      const now = (performance.now() - origin.current) / 1000;
      if (now >= total) {
        stop();
        setPlaying(false);
        setTime(null);
        return;
      }
      setTime(now);
      sync(now);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, total, sync, stop]);

  const play = () => {
    origin.current = performance.now() - from * 1000;
    setTime(from);
    setPlaying(true);
  };
  const pause = () => {
    stop();
    setPlaying(false);
    if (time !== null) {
      const here = spanAt(spans, time);
      if (here) onSelect(here.shot.id);
    }
  };
  const toggle = () => (playing ? pause() : play());

  const seek = (s: (typeof spans)[number], e: MouseEvent<HTMLButtonElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const frac = e.detail && box.width > 0 ? (e.clientX - box.left) / box.width : 0;
    const to = s.start + Math.min(Math.max(frac, 0), 0.999) * (s.end - s.start);
    stop();
    if (playing) jump.current = to;
    setTime(to);
    onSelect(s.shot.id);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== " " || e.repeat || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.target instanceof Element && e.target.closest(OWNS_SPACE)) return;
      e.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const shot = span?.shot;
  const { w } = frameSize(aspect);
  const picture = shot ? framePicture(shots, shot) : null;
  // Where 播放 goes from (the top until it has played or jumped).
  const clock = from;
  const subtitle = cues.find((c) => at !== null && at >= c.start && at < c.end);
  const sub = area?.subtitle ?? { top: 76, right: 0 };

  return (
    <section
      aria-label={t("preview.label")}
      className="flex flex-wrap items-center gap-4 rounded-lg border bg-card p-3"
    >
      <div className="shrink-0" style={{ width: w }}>
        {shot ? (
          <div
            role="img"
            aria-label={t("preview.frame", { id: shot.label, summary: shot.summary })}
          >
            <MediaThumb
              aspect={aspect}
              seed={picture?.from ?? shot.label}
              src={picture?.sha256 ? fileUrl(picture.sha256) : null}
              label={shot.label}
              overlay={
                <>
                  {showSafe && area ? <SafeAreaOverlay area={area} /> : null}
                  {picture?.from ? (
                    <span className="absolute top-1.5 right-1.5 rounded-sm bg-black/55 px-1 py-0.5 text-[10px] text-white">
                      {t("preview.tail", { id: picture.from })}
                    </span>
                  ) : null}
                  {subtitle ? (
                    <div
                      data-testid="preview-subtitle"
                      className="absolute left-[4%] text-center text-[11px] leading-snug font-bold text-white drop-shadow"
                      style={{ top: `${sub.top}%`, right: `${Math.max(sub.right, 4)}%` }}
                    >
                      {subtitle.text}
                    </div>
                  ) : null}
                </>
              }
            />
          </div>
        ) : null}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Button size="sm" aria-pressed={playing} onClick={toggle}>
            {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
            {t(playing ? "preview.pause" : "preview.play")}
          </Button>
          <span data-testid="preview-clock" className="font-mono text-xs tabular-nums">
            {t("preview.clock", {
              at: formatClock(clock, { pad: true }),
              total: formatClock(total, { pad: true }),
            })}
          </span>
          <span className="text-xs text-muted-foreground">
            {t("preview.total", { seconds: Math.round(total * 10) / 10 })}
          </span>
          <label className="ml-auto flex items-center gap-2 text-xs">
            <Checkbox checked={showSafe} onCheckedChange={(v) => onShowSafe(v === true)} />
            {t("preview.safe")}
          </label>
        </div>
        <div className="flex gap-1">
          {spans.map((s) => {
            const on = s.shot.id === shot?.id;
            const fill = on && at !== null ? (at - s.start) / (s.end - s.start) : 0;
            return (
              <button
                key={s.shot.id}
                type="button"
                aria-label={t("preview.shot", { id: s.shot.label, seconds: s.shot.duration_s })}
                aria-current={on ? "true" : undefined}
                onClick={(e) => seek(s, e)}
                style={{ flex: `${s.shot.duration_s} 1 0` }}
                className={cn(
                  "relative flex min-w-0 flex-col items-start overflow-hidden rounded-sm border px-1.5 py-1 text-left font-mono text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  on
                    ? "border-primary bg-tone-info-bg text-tone-info-fg"
                    : "border-transparent bg-media text-media-foreground",
                )}
              >
                {fill > 0 ? (
                  <span
                    aria-hidden
                    className="absolute inset-y-0 left-0 border-r-2 border-primary bg-primary/15"
                    style={{ width: `${fill * 100}%` }}
                  />
                ) : null}
                <span className="relative truncate">{s.shot.label}</span>
                <span className="relative opacity-70">
                  {t("preview.seconds", { n: s.shot.duration_s })}
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>{t("preview.keys")}</span>
          {missing ? (
            <span>
              {t("preview.missing", { count: missing })}
              {" · "}
              <Link to={dubPath} className="text-primary underline-offset-4 hover:underline">
                {t("preview.toDub")}
              </Link>
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}
