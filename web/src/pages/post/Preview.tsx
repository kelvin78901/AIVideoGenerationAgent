import { Pause, Play } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Shot } from "@/api/schemas/shots";
import type { Aspect } from "@/api/schemas/spec";
import type { Timeline } from "@/api/schemas/timeline";
import { MediaThumb } from "@/components/MediaThumb";
import { Button } from "@/components/ui/button";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * 预览 at the playhead: the clip (its keyframe when no take is adopted, marked as a stand-in)
 * and the subtitle on screen, with play / pause and the timecode.
 */
export function Preview({
  timeline,
  shots,
  aspect,
  playhead,
  playing,
  onToggle,
}: {
  timeline: Timeline;
  shots: Shot[];
  aspect: Aspect;
  playhead: number;
  playing: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation("post");
  const clip =
    timeline.clips.find((c) => playhead >= c.start_s && playhead < c.end_s) ??
    timeline.clips.at(-1);
  const sub = timeline.subtitles.find((s) => playhead >= s.start_s && playhead < s.end_s);
  const shot = shots.find((s) => s.id === clip?.shot_id);
  const wide = aspect === "16:9" || aspect === "21:9";

  return (
    <section
      aria-label={t("preview.label")}
      className={cn("flex shrink-0 flex-col gap-3", wide ? "w-full max-w-md" : "w-56")}
    >
      <MediaThumb
        aspect={aspect}
        seed={clip?.shot_label ?? ""}
        dashed={false}
        className="rounded-xl"
        overlay={
          <>
            {clip ? (
              <span className="absolute top-2.5 left-2.5 rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-neutral-900">
                {clip.shot_label}
              </span>
            ) : null}
            <div
              data-testid="preview-desc"
              className="absolute inset-x-4 top-1/2 -translate-y-1/2 text-center text-sm opacity-80"
            >
              {shot?.summary}
            </div>
            {sub ? (
              <div
                data-testid="preview-sub"
                className="absolute inset-x-3 bottom-12 text-center text-[15px] font-bold drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]"
              >
                {sub.text}
              </div>
            ) : null}
            {clip && !clip.version_id ? (
              <div className="absolute inset-x-2.5 bottom-2.5 rounded bg-tone-warn-bg px-2 py-1 text-center text-[11px] text-tone-warn-fg">
                {t("preview.placeholder")}
              </div>
            ) : null}
          </>
        }
      />
      <div className="flex items-center gap-3 px-1">
        <Button
          size="icon"
          className="size-11 rounded-full"
          onClick={onToggle}
          aria-label={t(playing ? "preview.pause" : "preview.play")}
        >
          {playing ? (
            <Pause className="fill-current" aria-hidden />
          ) : (
            <Play className="fill-current" aria-hidden />
          )}
        </Button>
        <span className="font-mono text-sm tabular-nums" data-testid="timecode">
          {t("preview.time", {
            now: formatClock(playhead, { pad: true }),
            total: formatClock(timeline.duration_s, { pad: true }),
          })}
        </span>
      </div>
    </section>
  );
}
