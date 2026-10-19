/**
 * Fake `/setup/*` and `/comfy/*` for page tests, built on what the Mock backend answers on its
 * sample machines (`test/data/setup.json`, exported by tests/api/test_web_fixtures.py). Scans and
 * installs finish in one task after the request, pushing `setup.progress` / `setup.log` over the
 * test's `FakeEventSource` like the real job does over SSE.
 */
import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { EventType } from "@/api/events";
import { ComfySnapshotSchema, ComfyViewSchema, type ComfySnapshot } from "@/api/schemas/comfy";
import { MessageSchema, type Message } from "@/api/schemas/common";
import {
  InstallRequestSchema,
  MachineProfileSchema,
  type ItemInstall,
  type SetupItem,
  type SetupLog,
} from "@/api/schemas/setup";
import data from "@/test/data/setup.json";
import { FakeEventSource } from "@/test/fakeEventSource";

export type SampleMachine = "pc" | "mac";
export type SnapshotFailure = "not_running" | "no_manager" | "forbidden" | "restart" | "failed";

function sample(m: SampleMachine) {
  const d = data[m];
  return {
    idle: MachineProfileSchema.parse(d.idle),
    scanned: MachineProfileSchema.parse(d.scanned),
    order: z.array(z.string()).parse(d.install.order),
    confirm: z.array(MessageSchema).parse(d.install.confirm),
    comfy: ComfyViewSchema.parse(d.comfy),
  };
}

const FAILING = data.failing;
const MANAGER = "comfy_manager";
const NOW = "2026-10-18T09:30:00Z";
/** The sample installs' download speed (setup/installer.py:FAKE_BPS). */
const FAKE_BPS = 25e6;

/** State of the fake; reset by `backend()`. Tests may read it, or set `snapshotFail`. */
export const fakeSetup = {
  machine: "pc" as SampleMachine,
  profile: sample("pc").idle,
  /** Ids installed so far: a rescan reports them as installed (SPEC 12.2). */
  installed: new Set<string>(),
  snapshots: [] as ComfySnapshot[],
  /** The ComfyUI view of the last finished scan. */
  comfyScanned: false,
  /** Makes every ComfyUI-Manager call fail with this reason. */
  snapshotFail: null as SnapshotFailure | null,
};

/** Starts over on a sample machine; `scanned` skips to the end of its first scan. */
export function resetFakeSetup(
  machine: SampleMachine = "pc",
  { scanned = false }: { scanned?: boolean } = {},
): void {
  const s = sample(machine);
  Object.assign(fakeSetup, {
    machine,
    profile: scanned ? s.scanned : s.idle,
    installed: new Set<string>(),
    snapshots: [],
    comfyScanned: scanned,
    snapshotFail: null,
  });
}

function emit(type: EventType, payload: unknown): void {
  for (const es of FakeEventSource.instances) if (!es.closed) es.emit(type, payload);
}

const log = (level: SetupLog["level"], code: string, params: Message["params"] = {}) =>
  emit("setup.log", { level, code, params });

const progress = (item: SetupItem | null = null) =>
  emit("setup.progress", { phase: fakeSetup.profile.phase, item: item && structuredClone(item) });

const error = (status: number, code: string, params: Record<string, unknown> = {}) =>
  HttpResponse.json({ detail: { code, params } }, { status });

const reply = (status = 200) => HttpResponse.json(fakeSetup.profile, { status });

const later = (fn: () => void) => setTimeout(fn, 0);

/** The item `id` of `profile`; a test that names a missing one fails here. */
export function itemOf(profile: { items: SetupItem[] }, id: string): SetupItem {
  const x = profile.items.find((i) => i.id === id);
  if (!x) throw new Error(`no item ${id}`);
  return x;
}

/** An install state without download figures (the backend sends them as null). */
export const installState = (
  state: ItemInstall["state"],
  pct = 0,
  error: Message | null = null,
): ItemInstall => ({
  state,
  pct,
  error,
  bytes_done: null,
  bytes_total: null,
  speed: null,
  eta_s: null,
  verifying: false,
});

function scanned(): SetupItem[] {
  return sample(fakeSetup.machine).scanned.items.map((x) =>
    fakeSetup.installed.has(x.id)
      ? {
          ...x,
          status: "ok",
          found: { code: "installed", params: {} },
          fix: null,
          installable: false,
        }
      : x,
  );
}

function newSnapshot(reason: ComfySnapshot["reason"], changes: Message[]): ComfySnapshot {
  const n = fakeSetup.snapshots.length + 1;
  const snap = ComfySnapshotSchema.parse({
    id: `snap${n}`,
    manager_name: `2026-10-18_09-3${n}-00_snapshot`,
    env_hash: sample(fakeSetup.machine).comfy.comfy?.env_hash ?? null,
    reason,
    changes,
    created_at: NOW,
    restored_at: null,
  });
  fakeSetup.snapshots.unshift(snap);
  return snap;
}

/** The install job: a snapshot before the first change to ComfyUI, then each queued item. */
function runInstall(): void {
  const p = fakeSetup.profile;
  const info = p.install;
  if (!info) return;
  for (const id of info.items) {
    const x = p.items.find((i) => i.id === id);
    if (!x?.install || x.install.state !== "queued") continue;
    x.install.state = "running";
    log("info", "start", { item: id });
    progress(x);
    let failure: Message | null = null;
    if (x.touches_comfy && id !== MANAGER) {
      if (!info.snapshot && !info.snapshot_error) {
        if (fakeSetup.snapshotFail) {
          info.snapshot_error = { code: `snapshot_${fakeSetup.snapshotFail}`, params: {} };
          log("warn", "snapshot_failed", { reason: fakeSetup.snapshotFail });
        } else {
          const snap = newSnapshot("install", info.changes);
          info.snapshot = snap.id;
          log("ok", "snapshot", { name: snap.manager_name });
        }
      }
      failure = info.snapshot_error;
    }
    if (!failure && id === FAILING.item) failure = { code: FAILING.error, params: {} };
    if (failure) {
      x.install = installState("failed", failure.code === FAILING.error ? FAILING.pct : 0, failure);
      log("warn", x.required ? "fail" : "fail_optional", { item: id });
    } else {
      x.install = installState("done", 100);
      fakeSetup.installed.add(id);
      if (x.size_bytes) p.download_bps = FAKE_BPS; // what its download measured
      log("ok", "done", { item: id });
    }
    progress(x);
  }
  p.phase = "done";
  log("ok", "finish");
  progress();
}

function findQueued(id: string) {
  return fakeSetup.profile.items.find((x) => x.id === id && x.install);
}

export function setupHandlers() {
  return [
    http.get("*/api/v1/setup/profile", () => reply()),

    http.post("*/api/v1/setup/scan", () => {
      const p = fakeSetup.profile;
      if (p.phase === "installing") return error(409, "setup_busy");
      const result = scanned();
      p.phase = "scanning";
      p.items = result.map((x) => ({
        ...x,
        status: "checking",
        found: null,
        fix: null,
        installable: false,
      }));
      later(() => {
        p.items.forEach((_, i) => {
          p.items[i] = structuredClone(result[i] as SetupItem);
          progress(p.items[i]);
        });
        const done = sample(fakeSetup.machine).scanned;
        Object.assign(p, {
          phase: "scanned",
          scanned_at: NOW,
          recommendation: done.recommendation,
          // The scan's short download, unless an install measured the speed already.
          download_bps: p.download_bps ?? done.download_bps,
        });
        fakeSetup.comfyScanned = true;
        progress();
      });
      return reply(202);
    }),

    http.post("*/api/v1/setup/install", async ({ request }) => {
      const body = InstallRequestSchema.safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      const p = fakeSetup.profile;
      if (p.phase === "scanning" || p.phase === "installing") return error(409, "setup_busy");
      const s = sample(fakeSetup.machine);
      const installable = new Set(p.items.filter((x) => x.installable).map((x) => x.id));
      const chosen = new Set(body.data.items.filter((id) => installable.has(id)));
      // The sample machines need no automatic ComfyUI-Manager: PC has it, Mac has no ComfyUI.
      const order = s.order.filter((id) => chosen.has(id));
      if (!order.length) return error(422, "nothing_selected");
      const confirm = s.confirm.filter((m) => order.includes(String(m.params.item)));
      p.phase = "installing";
      p.install = {
        ...body.data,
        items: order,
        confirm,
        changes: confirm.filter((m) => m.code === "comfy_change"),
        snapshot: null,
        snapshot_error: null,
      };
      for (const x of p.items) x.install = order.includes(x.id) ? installState("queued") : null;
      later(() => {
        log("info", "mirror", { mirror: body.data.mirror, dir: body.data.dir });
        if (confirm.length) log("warn", "confirm");
        else runInstall();
        progress();
      });
      return reply(202);
    }),

    http.post("*/api/v1/setup/install/confirm", () => {
      const info = fakeSetup.profile.install;
      if (fakeSetup.profile.phase !== "installing" || !info?.confirm.length)
        return error(409, "setup_no_confirm");
      info.confirm = [];
      later(runInstall);
      return reply();
    }),

    http.post("*/api/v1/setup/install/cancel", () => {
      const p = fakeSetup.profile;
      if (p.phase !== "installing" || !p.install?.confirm.length)
        return error(409, "setup_no_confirm");
      p.install.confirm = [];
      p.phase = "scanned";
      for (const x of p.items) x.install = null;
      later(() => {
        log("info", "cancel");
        progress();
      });
      return reply();
    }),

    http.post<{ id: string }>("*/api/v1/setup/items/:id/retry", ({ params }) => {
      const x = findQueued(params.id);
      if (!x?.install) return error(404, "setup_item_not_found", { id: params.id });
      if (x.install.state !== "failed" && x.install.state !== "skipped")
        return error(409, "setup_item_state", { id: params.id });
      x.install = installState("queued");
      const p = fakeSetup.profile;
      if (p.install) p.install.snapshot_error = null;
      p.phase = "installing";
      later(() => {
        log("info", "retry", { item: x.id });
        progress(x);
        runInstall();
      });
      return reply();
    }),

    http.post<{ id: string }>("*/api/v1/setup/items/:id/skip", ({ params }) => {
      const x = findQueued(params.id);
      if (!x?.install) return error(404, "setup_item_not_found", { id: params.id });
      if (x.install.state !== "failed" && x.install.state !== "queued")
        return error(409, "setup_item_state", { id: params.id });
      x.install.state = "skipped";
      later(() => {
        log("info", "skip", { item: x.id });
        progress(x);
      });
      return reply();
    }),

    http.post("*/api/v1/dev/setup/machine", async ({ request }) => {
      const body = z.object({ machine: z.enum(["pc", "mac"]) }).safeParse(await request.json());
      if (!body.success) return error(422, "invalid_request");
      resetFakeSetup(body.data.machine);
      later(() => progress());
      return reply();
    }),

    http.get("*/api/v1/comfy/env", () => {
      const view = sample(fakeSetup.machine).comfy;
      return HttpResponse.json(
        fakeSetup.comfyScanned
          ? view
          : { scanned_at: null, simulated: true, comfy: null, env: null },
      );
    }),

    http.get("*/api/v1/comfy/snapshots", () => HttpResponse.json(fakeSetup.snapshots)),

    http.post("*/api/v1/comfy/snapshots", () => {
      if (!fakeSetup.comfyScanned || !sample(fakeSetup.machine).comfy.comfy)
        return error(409, "comfy_not_found");
      if (fakeSetup.snapshotFail)
        return error(409, "comfy_snapshot_failed", { reason: fakeSetup.snapshotFail });
      return HttpResponse.json(newSnapshot("manual", []), { status: 201 });
    }),

    http.post<{ id: string }>("*/api/v1/comfy/snapshots/:id/restore", ({ params }) => {
      const snap = fakeSetup.snapshots.find((s) => s.id === params.id);
      if (!snap) return error(404, "comfy_snapshot_not_found", { id: params.id });
      if (fakeSetup.profile.phase === "installing") return error(409, "setup_busy");
      if (fakeSetup.snapshotFail)
        return error(409, "comfy_snapshot_failed", { reason: fakeSetup.snapshotFail });
      snap.restored_at = NOW;
      return HttpResponse.json({ snapshot: snap, restart_required: true });
    }),
  ];
}
