import { fileUrl } from "@/api/client";
import type { Dub } from "@/api/schemas/dub";
import type { Shot } from "@/api/schemas/shots";
import type { Aspect } from "@/api/schemas/spec";
import { ASPECT_RATIO } from "@/lib/safeArea";

/** Before the first line of a shot (`pipeline/timing.py` PRE_ROLL_S). */
export const PRE_ROLL_S = 0.3;

/** The animatic's frame: portrait and square specs this tall, landscape ones this wide. */
const FRAME_H = 224;
const FRAME_W = 300;

export function frameSize(aspect: Aspect): { w: number; h: number } {
  const [w, h] = ASPECT_RATIO[aspect];
  return h >= w
    ? { w: Math.round((FRAME_H * w) / h), h: FRAME_H }
    : { w: FRAME_W, h: Math.round((FRAME_W * h) / w) };
}

/** A shot's place on the episode's clock. */
export interface Span {
  shot: Shot;
  start: number;
  end: number;
}

/** A spoken line: its subtitle and, once dubbed, its audio. */
export interface Cue {
  lineId: string;
  start: number;
  end: number;
  text: string;
  /** null = not dubbed yet: the subtitle alone. */
  src: string | null;
}

/**
 * The episode as the animatic plays it: the shots one after another for as long as each runs;
 * each shot's spoken lines (their dub, in the order it films them) start `PRE_ROLL_S` into it
 * and follow one another, cut at the shot's end.
 */
export function timeline(shots: Shot[], dub: Dub | undefined) {
  const lines = new Map((dub?.lines ?? []).map((x) => [x.line_id, x]));
  const spans: Span[] = [];
  const cues: Cue[] = [];
  let at = 0;
  for (const shot of shots) {
    const end = at + shot.duration_s;
    spans.push({ shot, start: at, end });
    let cue = at + PRE_ROLL_S;
    for (const id of shot.line_ids) {
      const line = lines.get(id);
      if (!line || cue >= end) continue;
      cues.push({
        lineId: id,
        start: cue,
        end: Math.min(cue + line.seconds, end),
        text: line.text,
        src: line.audio ? fileUrl(line.audio.sha256) : null,
      });
      cue += line.seconds;
    }
    at = end;
  }
  return { spans, cues, total: at, missing: cues.filter((c) => !c.src).length };
}

export const spanAt = (spans: Span[], t: number) =>
  spans.find((s) => t >= s.start && t < s.end) ?? spans[spans.length - 1];

/** What a shot's frame shows: its picked keyframe, or (a continuous shot, until M5 has its
 * video's last frame) the keyframe of the shot it continues. */
export function framePicture(
  shots: Shot[],
  shot: Shot,
): { sha256: string | null; from: string | null } {
  let s: Shot | undefined = shot;
  for (let hop = 0; s?.shot_type === "continuous" && hop < shots.length; hop++) {
    const label: string | null = s.tail_from;
    s = shots.find((x) => x.label === label);
  }
  return {
    sha256: s && s.shot_type !== "continuous" ? s.keyframe_sha256 : null,
    from: shot.shot_type === "continuous" ? shot.tail_from : null,
  };
}
