import { useTranslation } from "react-i18next";

import type { AudioSegment, Timeline } from "@/api/schemas/timeline";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";

type TrackId = "video" | "dialogue" | "ambience" | "music" | "subtitle";
const TRACKS: TrackId[] = ["video", "dialogue", "ambience", "music", "subtitle"];

interface Segment {
  id: string;
  start: number;
  end: number;
  label: string;
  className: string;
  onPick: () => void;
}

const audioStyle: Record<AudioSegment["source"], string> = {
  native: "border-border bg-muted text-muted-foreground",
  dub: "border-tone-info-border bg-tone-info-bg text-tone-info-fg",
  sfx: "border-tone-warn-border bg-tone-warn-bg text-tone-warn-fg",
  music:
    "border-violet-300 bg-violet-50 text-violet-900 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-200",
};

/**
 * 5 轨时间线: picture, dialogue, ambience / sfx, music, subtitles on one time axis with the
 * playhead. Picking a clip or a line selects the clip; sfx / music / subtitles open their
 * component in the Inspector.
 */
export function TimelineView({
  timeline,
  playhead,
  selectedClipId,
  onSelectClip,
  onPickComponent,
  onNativeAudio,
}: {
  timeline: Timeline;
  playhead: number;
  selectedClipId: string | undefined;
  onSelectClip: (clipId: string) => void;
  onPickComponent: (componentId: string) => void;
  onNativeAudio: (label: string) => void;
}) {
  const { t } = useTranslation("post");
  const total = timeline.duration_s || 1;
  const pct = (s: number) => `${((s / total) * 100).toFixed(3)}%`;
  const clipOfShot = (shotId: string | null) =>
    timeline.clips.find((c) => c.shot_id === shotId)?.id;

  const audio = (track: AudioSegment["track"]): Segment[] =>
    timeline.audio
      .filter((a) => a.track === track)
      .map((a) => ({
        id: a.id,
        start: a.start_s,
        end: a.end_s,
        label: a.source === "native" && track === "ambience" ? t("timeline.native", a) : a.label,
        // Lines are blue whether the video model voiced them or they were dubbed first.
        className: audioStyle[track === "dialogue" ? "dub" : a.source],
        onPick: () => {
          const clip = clipOfShot(a.shot_id);
          if (a.component_id) onPickComponent(a.component_id);
          else if (clip) onSelectClip(clip);
          else onNativeAudio(a.label);
        },
      }));

  const segments: Record<TrackId, Segment[]> = {
    video: timeline.clips.map((c) => ({
      id: c.id,
      start: c.start_s,
      end: c.end_s,
      label: c.shot_label,
      className: cn(
        c.version_id
          ? "border-neutral-800 bg-neutral-800 text-neutral-50 dark:border-neutral-600 dark:bg-neutral-700"
          : "border-dashed border-tone-warn-border bg-card text-tone-warn-fg",
        c.id === selectedClipId && "z-10 ring-2 ring-primary",
      ),
      onPick: () => onSelectClip(c.id),
    })),
    dialogue: audio("dialogue"),
    ambience: audio("ambience"),
    music: audio("music"),
    subtitle: timeline.subtitles.map((s) => ({
      id: s.id,
      start: s.start_s,
      end: s.end_s,
      label: s.text,
      className: "border-border bg-card text-foreground",
      onPick: () => onPickComponent("sub"),
    })),
  };

  const ticks: number[] = [];
  for (let s = 0; s < total; s += 5) ticks.push(s);

  return (
    <section aria-label={t("timeline.label")} className="rounded-xl border bg-card px-4 py-3.5">
      <div className="grid grid-cols-[72px_1fr] gap-x-3 gap-y-2">
        <div />
        <div className="relative h-5 font-mono text-[11px] text-muted-foreground">
          {ticks.map((s) => (
            <span key={s} className="absolute" style={{ left: pct(s) }}>
              {formatClock(s, { pad: true })}
            </span>
          ))}
        </div>
        {TRACKS.map((track) => {
          const name = t(`timeline.tracks.${track}`);
          return (
            <div key={track} className="contents">
              <div className="self-center text-xs text-muted-foreground">{name}</div>
              <div className="relative h-9 rounded-md bg-muted/50">
                {segments[track].map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    onClick={g.onPick}
                    aria-label={t("timeline.segment", { track: name, label: g.label })}
                    title={g.label}
                    className={cn(
                      "absolute inset-y-0.5 overflow-hidden rounded border px-1.5 text-left text-[11px] text-ellipsis whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      g.className,
                    )}
                    style={{ left: pct(g.start), width: pct(g.end - g.start) }}
                  >
                    {g.label}
                  </button>
                ))}
                {/* The playhead runs through every lane; the overhang bridges the gaps. */}
                <div
                  aria-hidden
                  data-testid={track === "video" ? "playhead" : undefined}
                  className="pointer-events-none absolute -inset-y-1 z-20 w-0.5 bg-tone-warn-fg"
                  style={{ left: pct(playhead) }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
