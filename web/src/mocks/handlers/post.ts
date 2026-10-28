import { http } from "msw";

import type { Job } from "@/api/schemas/jobs";
import {
  ClipPatchSchema,
  ExportRequestSchema,
  SubtitlePatchSchema,
  type Clip,
  type ExportCheck,
  type Timeline,
} from "@/api/schemas/timeline";
import { getDb } from "@/mocks/db";
import { defaultClip, type Anchor } from "@/mocks/fixtures/demo/post";
import { demoShots, demoVideos } from "@/mocks/handlers/shots";
import { demoError, demoJson, v1 } from "@/mocks/http";

const clipId = (shotId: string) => `demo-clip-${shotId}`;

/** The backend's shots of the episode and their takes, fresh. */
async function readShots(request: Request, episodeId: string): Promise<void> {
  await Promise.all([demoShots(request, episodeId), demoVideos(request)]);
}

/** Lays the shots end to end and places the anchored audio and subtitles on them. The shots
 * and their takes are the backend's as last read (`readShots`): handlers read them first. */
export function buildTimeline(episodeId: string): Timeline {
  const db = getDb();
  const shots = db.shots.filter((s) => s.episode_id === episodeId);
  const starts = new Map<string, number>();
  let t = 0;
  const clips: Clip[] = shots.map((s) => {
    starts.set(s.label, t);
    const video = db.videos.find((p) => p.id === s.video_product_id);
    const clip: Clip = {
      id: clipId(s.id),
      shot_id: s.id,
      shot_label: s.label,
      start_s: t,
      end_s: t + s.duration_s,
      version_id: video?.adopted_version_id ?? null,
      ...defaultClip,
      ...db.post.clips[s.id],
    };
    t += s.duration_s;
    return clip;
  });
  const total = t;
  const place = (at: Anchor) => {
    const start = (at.shot ? (starts.get(at.shot) ?? 0) : 0) + at.offset_s;
    return { start_s: start, end_s: at.duration_s === null ? total : start + at.duration_s };
  };
  const shotOf = (at: Anchor) => shots.find((s) => s.label === at.shot)?.id ?? null;
  // Episodes without post data yet get just the picture track.
  const own = episodeId === db.post.episode_id;
  return {
    episode_id: episodeId,
    duration_s: total,
    clips,
    audio: own
      ? db.post.audio.map(({ at, ...a }) => ({
          ...a,
          ...place(at),
          shot_id: a.track === "dialogue" ? shotOf(at) : null,
        }))
      : [],
    subtitles: own
      ? db.post.subtitles.map((s) => ({
          id: s.id,
          text: s.text,
          line_id: s.line_id,
          edited: s.edited,
          ...place(s.at),
        }))
      : [],
  };
}

export function exportChecks(episodeId: string): ExportCheck[] {
  const placeholders = buildTimeline(episodeId).clips.filter((c) => !c.version_id).length;
  return [
    { status: "pass", message: { code: "loudness", params: { lufs: -14 } } },
    { status: "pass", message: { code: "frames", params: {} } },
    placeholders
      ? { status: "warn", message: { code: "placeholders", params: { count: placeholders } } }
      : { status: "pass", message: { code: "all_adopted", params: {} } },
  ];
}

const episodeExists = (id: string) => getDb().episodes.some((e) => e.id === id);

export const postHandlers = [
  http.get(v1("/episodes/:id/timeline"), async ({ params, request }) => {
    const id = String(params.id);
    if (!episodeExists(id)) return demoError(404, "episode_not_found", { id });
    await readShots(request, id);
    return demoJson(buildTimeline(id));
  }),

  http.patch(v1("/clips/:id"), async ({ params, request }) => {
    const shot = getDb().shots.find((s) => clipId(s.id) === String(params.id));
    if (!shot) return demoError(404, "clip_not_found", { id: params.id });
    const body = ClipPatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const clips = getDb().post.clips;
    clips[shot.id] = { ...defaultClip, ...clips[shot.id], ...body.data };
    await readShots(request, shot.episode_id);
    return demoJson(buildTimeline(shot.episode_id));
  }),

  http.patch(v1("/subtitles/:id"), async ({ params, request }) => {
    const sub = getDb().post.subtitles.find((s) => s.id === String(params.id));
    if (!sub) return demoError(404, "subtitle_not_found", { id: params.id });
    const body = SubtitlePatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    sub.text = body.data.text;
    sub.edited = sub.text !== sub.source_text;
    await readShots(request, getDb().post.episode_id);
    return demoJson(buildTimeline(getDb().post.episode_id));
  }),

  http.get(v1("/episodes/:id/export/checks"), async ({ params, request }) => {
    const id = String(params.id);
    if (!episodeExists(id)) return demoError(404, "episode_not_found", { id });
    await readShots(request, id);
    return demoJson({ checks: exportChecks(id) });
  }),

  // Export → job. Like the demo runs, it is not pushed into the real job list.
  http.post(v1("/episodes/:id/export"), async ({ params, request }) => {
    const id = String(params.id);
    if (!episodeExists(id)) return demoError(404, "episode_not_found", { id });
    const body = ExportRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const job: Job = {
      id: `demo-job-export-${body.data.format}-${Date.now()}`,
      series_id: getDb().episodes.find((e) => e.id === id)?.series_id ?? null,
      product_id: null,
      component_id: null,
      kind: `export.${body.data.format}`,
      queue: "cpu",
      state: "queued",
      priority: 0,
      attempt: 0,
      max_attempts: 1,
      params: { episode_id: id, format: body.data.format },
      result: null,
      error: null,
      depends_on: [],
      est_cost_usd: 0,
      fallback_from_job_id: null,
      created_at: new Date().toISOString(),
      started_at: null,
      finished_at: null,
    };
    return demoJson(job);
  }),
];
