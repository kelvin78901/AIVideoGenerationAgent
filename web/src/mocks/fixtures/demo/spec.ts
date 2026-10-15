/** Output spec of the demo series: 国内短剧 · 9:16 · 1080p · 24 fps (SPEC 13.1 defaults). */
import type { OutputSpec } from "@/api/schemas/spec";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";

export const spec: OutputSpec = {
  series_id: DEMO_SERIES_ID,
  platform: "cn",
  aspect: "9:16",
  delivery: "1080p",
  fps: 24,
  episode_len: "short",
  subtitles: "both",
  audio: { sample_rate: 48000, lufs: -14, peak_dbtp: -1 },
  codec: "h264",
  ai_mark: true,
  derive: null,
  // Locked when the first keyframe (1-01 v2) was adopted.
  locked_at: "2026-10-14T11:02:00+08:00",
  dims: { delivery: { w: 1080, h: 1920 }, draft: { w: 768, h: 1366 } },
};
