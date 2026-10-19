/**
 * Sync (SPEC 14): settings, detection, a manual run that reports progress as `sync.updated`,
 * the log, and episode 1's ComfyUI board.
 */
import { http } from "msw";
import { z } from "zod";

import { api } from "@/api/client";
import { OutputSpecSchema } from "@/api/schemas/spec";
import {
  SyncSettingsPatchSchema,
  type SyncRun,
  type SyncSettings,
  type SyncTargetId,
} from "@/api/schemas/sync";
import { getDb, type DemoDb } from "@/mocks/db";
import { demoTiming, emitDemoEvent, repeatDemo } from "@/mocks/events";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import { spec as demoSpec } from "@/mocks/fixtures/demo/spec";
import { SIZE_ROW, SYNC_ROOT, SYNC_RUN, syncBoard } from "@/mocks/fixtures/demo/sync";
import { demoError, demoJson, v1 } from "@/mocks/http";

const RunRequestSchema = z.object({ episode_id: z.string() });

/** SPEC 14.1 folder layout for the example file (1-03's adopted video). */
function settings(d: DemoDb): SyncSettings {
  const { targets, rules } = d.sync;
  const dir = rules.org === "shot" ? `${SYNC_ROOT}E01\\S01\\1-03\\` : `${SYNC_ROOT}E01\\视频\\`;
  return {
    targets,
    rules,
    preview: { dir, files: ["E01_S01_1-03_video_v2.mp4", "E01_S01_1-03_video_v2.json"] },
  };
}

/** Where a run's files went: the enabled targets that can receive (ComfyUI board, folders). */
const deliveredTo = (d: DemoDb) =>
  d.sync.targets
    .filter((t) => t.enabled && t.state !== "missing")
    .map((t) => ({ code: t.id, params: {} }));

export const syncHandlers = [
  http.get(v1("/sync/targets"), () => demoJson(settings(getDb()))),

  http.put(v1("/sync/targets"), async ({ request }) => {
    const body = SyncSettingsPatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const d = getDb();
    for (const patch of body.data.targets ?? []) {
      const target = d.sync.targets.find((t) => t.id === patch.id);
      if (!target) return demoError(404, "sync_target_not_found", { id: patch.id });
      if (patch.enabled && target.state === "missing")
        return demoError(409, "sync_target_missing", { id: patch.id });
      if (patch.mode && target.unavailable_modes[patch.mode])
        return demoError(409, "sync_mode_unavailable", { id: patch.id, mode: patch.mode });
      if (patch.enabled !== undefined) target.enabled = patch.enabled;
      if (patch.mode) target.mode = patch.mode;
    }
    d.sync.rules = { ...d.sync.rules, ...body.data.rules };
    return demoJson(settings(d));
  }),

  // 「重新检测」: the demo machine never has Eagle running.
  http.post<{ id: SyncTargetId }>(v1("/sync/targets/:id/detect"), ({ params }) => {
    const target = getDb().sync.targets.find((t) => t.id === params.id);
    if (!target) return demoError(404, "sync_target_not_found", { id: params.id });
    if (target.id === "eagle")
      target.status = { code: "eagle_no_response", params: { port: 41595 } };
    return demoJson(target);
  }),

  http.post(v1("/sync/run"), async ({ request }) => {
    const body = RunRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const d = getDb();
    if (d.sync.run?.state === "running") return demoError(409, "sync_busy");
    d.sync.runs += 1;
    const run: SyncRun = {
      run_id: `sync-${d.sync.runs}`,
      state: "running",
      done: 0,
      total: SYNC_RUN.total,
    };
    d.sync.run = run;
    repeatDemo(
      demoTiming.syncTickMs,
      () => {
        run.done += 1;
        const finished = run.done >= run.total;
        if (finished) {
          run.state = "done";
          d.sync.log.unshift({
            id: `sl-run-${d.sync.runs}`,
            at: new Date().toISOString(),
            what: { code: "manual", params: { files: run.total, added: SYNC_RUN.added } },
            to: deliveredTo(d),
          });
          emitDemoEvent("toast", {
            level: "success",
            code: "sync_done",
            params: { files: run.total, added: SYNC_RUN.added },
          });
        }
        emitDemoEvent("sync.updated", { ...run });
        return !finished;
      },
      () => getDb() === d && d.sync.run === run,
    );
    return demoJson(run, { status: 202 });
  }),

  // ?series=<id>
  http.get(v1("/sync/log"), () => demoJson(getDb().sync.log)),

  // ?episode=<id>
  http.get(v1("/sync/board"), async ({ request }) => {
    const episode = new URL(request.url).searchParams.get("episode");
    if (episode !== EP1) return demoError(404, "episode_not_found", { id: episode ?? "" });
    const board = structuredClone(syncBoard);
    // The 镜头 node's size follows the real spec (M1); the fixture if the backend is down.
    const spec = await api(`/series/${DEMO_SERIES_ID}/spec`, OutputSpecSchema).catch(
      () => demoSpec,
    );
    const row = board.nodes.find((n) => n.id === SIZE_ROW.node)?.rows[SIZE_ROW.row];
    if (row) row.label = `${spec.dims.delivery.w}×${spec.dims.delivery.h} · ${spec.fps}fps`;
    return demoJson(board);
  }),
];
