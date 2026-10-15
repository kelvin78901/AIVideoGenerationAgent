/**
 * Episode 1 post (prototype Post.dc.html): per-clip settings, the audio and subtitle tracks
 * anchored to shots (so they follow shot durations), and the music / sfx / subtitle products.
 * With the storyboard's durations the timeline matches the prototype: 34 s, 林晚 11–13.5 s,
 * 画外音 18–21 s, 门轴声 25–29 s, 卡点 33–34 s, 音乐 17–34 s.
 */
import type { Product } from "@/api/schemas/products";
import type { AudioSegment, Clip, Subtitle } from "@/api/schemas/timeline";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { demoAt, demoVersion } from "@/mocks/fixtures/demo/products";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

export type ClipSettings = Pick<
  Clip,
  "trim_head" | "transition" | "dialogue_volume" | "ambience_volume"
>;

export const defaultClip: ClipSettings = {
  trim_head: true,
  transition: "cut",
  dialogue_volume: 80,
  ambience_volume: 45,
};

/** Where a segment sits: from `offset_s` into a shot, for `duration_s` or to the end. */
export interface Anchor {
  /** Shot label; null = the start of the episode. */
  shot: string | null;
  offset_s: number;
  /** null = to the end of the episode. */
  duration_s: number | null;
}

export type AnchoredAudio = Omit<AudioSegment, "start_s" | "end_s" | "shot_id"> & {
  at: Anchor;
};
export type AnchoredSubtitle = Omit<Subtitle, "start_s" | "end_s"> & {
  at: Anchor;
  /** The script's words; `edited` = the text differs from them. */
  source_text: string;
};

export const audio: AnchoredAudio[] = [
  {
    id: "demo-a-line-1",
    track: "dialogue",
    at: { shot: "1-04", offset_s: 1, duration_s: 2.5 },
    label: "林晚：……周屿？",
    source: "native",
    component_id: null,
  },
  {
    id: "demo-a-line-2",
    track: "dialogue",
    at: { shot: "1-06", offset_s: 1, duration_s: 3 },
    label: "画外音：三年了。他凭什么。",
    source: "dub",
    component_id: null,
  },
  {
    id: "demo-a-rain",
    track: "ambience",
    at: { shot: null, offset_s: 0, duration_s: null },
    label: "雨声",
    source: "native",
    component_id: null,
  },
  {
    id: "demo-a-door",
    track: "ambience",
    at: { shot: "1-08", offset_s: 1, duration_s: 4 },
    label: "门轴声 ×2",
    source: "sfx",
    component_id: "sfx",
  },
  {
    id: "demo-a-hit",
    track: "ambience",
    at: { shot: "1-09", offset_s: 3, duration_s: 1 },
    label: "卡点",
    source: "sfx",
    component_id: "sfx",
  },
  {
    id: "demo-a-music",
    track: "music",
    at: { shot: "1-06", offset_s: 0, duration_s: null },
    label: "钢琴 · 压低 · 卡点停",
    source: "music",
    component_id: "music",
  },
];

export const subtitles: AnchoredSubtitle[] = [
  {
    id: "demo-sub-1",
    at: { shot: "1-04", offset_s: 1, duration_s: 2.5 },
    text: "……周屿？",
    source_text: "……周屿？",
    line_id: "demo-b5",
    edited: false,
  },
  {
    id: "demo-sub-2",
    at: { shot: "1-06", offset_s: 1, duration_s: 3 },
    text: "三年了。他凭什么。",
    source_text: "三年了。他凭什么。",
    line_id: "demo-b10",
    edited: false,
  },
];

function postProduct(
  componentId: string,
  slot: Product["slot"],
  v: { model: string; at: string; adopted: boolean; payload: Record<string, unknown> },
): Product {
  const id = `demo-p-${componentId}-e1`;
  const v1 = demoVersion(id, componentId, {
    n: 1,
    origin: "run",
    model: v.model,
    at: demoAt(v.at),
    payload: v.payload,
  });
  return {
    id,
    series_id: DEMO_SERIES_ID,
    owner_type: "episode",
    owner_id: EP1,
    slot,
    component_id: componentId,
    current_version_id: v1.id,
    adopted_version_id: v.adopted ? v1.id : null,
    locked_hash: null,
    status: v.adopted ? "adopted" : "ready",
    versions: [v1],
    prompt: null,
    estimate: null,
    running: null,
  };
}

/** 配乐 v1 ElevenLabs Music 12:05 已采纳; 音效 v1 MMAudio 12:08 草稿; 字幕 v1 Whisper 12:10 已采纳. */
export const postProducts: Product[] = [
  postProduct("music", "music", {
    model: "elevenlabs/music",
    at: "12:05",
    adopted: true,
    payload: { segments: 1, seconds: 17 },
  }),
  postProduct("sfx", "sfx", {
    model: "local/mmaudio",
    at: "12:08",
    adopted: false,
    payload: { items: 3 },
  }),
  postProduct("sub", "subtitles", {
    model: "local/whisper-large-v3",
    at: "12:10",
    adopted: true,
    payload: { lines: 2 },
  }),
];
