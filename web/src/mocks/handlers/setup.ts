/**
 * First run (SPEC 12): the scan reveals one item at a time and the install advances one queued
 * item at a time, both pushed as `setup.progress` / `setup.log` events like the backend will.
 */
import { http } from "msw";
import { z } from "zod";

import {
  InstallRequestSchema,
  type MachineProfile,
  type SetupItem,
  type SetupLog,
} from "@/api/schemas/setup";
import { getDb, type DemoDb } from "@/mocks/db";
import { demoTiming, emitDemoEvent } from "@/mocks/events";
import {
  FAILING_ITEM,
  idleProfile,
  recommendations,
  scanResults,
  type DemoItem,
} from "@/mocks/fixtures/demo/setup";
import { demoError, demoJson, v1 } from "@/mocks/http";

const DemoMachineSchema = z.object({ machine: z.enum(["pc", "mac"]) });

const busy = (p: MachineProfile) => p.phase === "scanning" || p.phase === "installing";
const scanOf = (d: DemoDb) => scanResults[d.setup.machine];

function resultOf(d: DemoDb, x: DemoItem): SetupItem {
  const { id, group, name, status, found, fix, required, installable } = x;
  const item = { id, group, name, status, found, fix, required, installable };
  // A rescan after an install only reports the difference (SPEC 12.2).
  if (d.setup.installed.includes(x.id))
    return {
      ...item,
      status: "ok",
      found: { code: "installed", params: {} },
      fix: null,
      install: null,
    };
  return { ...item, install: null };
}

function log(level: SetupLog["level"], code: string, params: SetupLog["params"] = {}) {
  emitDemoEvent("setup.log", { level, code, params } satisfies SetupLog);
}

function progress(p: MachineProfile, item: SetupItem | null = null) {
  emitDemoEvent("setup.progress", { phase: p.phase, item: item && structuredClone(item) });
}

/** Repeats `step` until it returns false, a newer scan / install starts, or the db is reset. */
function every(d: DemoDb, ms: number, step: () => boolean) {
  const run = d.setup.run;
  const timer = setInterval(() => {
    if (getDb() !== d || d.setup.run !== run || !step()) clearInterval(timer);
  }, ms);
}

function startScan(d: DemoDb) {
  d.setup.run += 1;
  d.setup.pumping = false;
  const list = scanOf(d);
  const p = d.profile;
  p.phase = "scanning";
  p.items = list.map((x) => ({
    ...resultOf(d, x),
    status: "checking",
    found: null,
    fix: null,
  }));
  let shown = 0;
  every(d, demoTiming.setupScanMs, () => {
    const x = list[shown];
    if (!x) {
      p.phase = "scanned";
      p.scanned_at = new Date().toISOString();
      p.recommendation = recommendations[d.setup.machine];
      progress(p);
      return false;
    }
    p.items[shown] = resultOf(d, x);
    progress(p, p.items[shown]);
    shown += 1;
    return true;
  });
}

/** Works through the queue in order (the GPU queue runs one job at a time, CLAUDE.md rule 8). */
function pump(d: DemoDb) {
  if (d.setup.pumping) return;
  d.setup.pumping = true;
  const p = d.profile;
  every(d, demoTiming.setupTickMs, () => {
    const order = p.install?.items ?? [];
    const item = order
      .map((id) => p.items.find((x) => x.id === id))
      .find((x) => x?.install?.state === "queued" || x?.install?.state === "running");
    if (!item?.install) {
      p.phase = "done";
      d.setup.pumping = false;
      progress(p);
      log("ok", "finish");
      return false;
    }
    const inst = item.install;
    if (inst.state === "queued") {
      inst.state = "running";
      inst.pct = 0;
      log("info", "start", { item: item.id });
    } else {
      const dl = scanOf(d).find((x) => x.id === item.id)?.dl;
      const next = inst.pct + (dl ? 10 : 34);
      if (item.id === FAILING_ITEM && next >= 60) {
        Object.assign(inst, { state: "failed", pct: 60, error: { code: "no_wheel", params: {} } });
        log("warn", item.required ? "fail" : "fail_optional", { item: item.id });
      } else if (next >= 100) {
        Object.assign(inst, { state: "done", pct: 100 });
        d.setup.installed.push(item.id);
        log("ok", "done", { item: item.id });
      } else inst.pct = next;
    }
    progress(p, item);
    return true;
  });
}

function findItem(id: string) {
  return getDb().profile.items.find((x) => x.id === id);
}

export const setupHandlers = [
  http.get(v1("/setup/profile"), () => demoJson(getDb().profile)),

  http.post(v1("/setup/scan"), () => {
    const d = getDb();
    if (d.profile.phase === "installing") return demoError(409, "setup_busy");
    startScan(d);
    return demoJson(d.profile, { status: 202 });
  }),

  http.post(v1("/setup/install"), async ({ request }) => {
    const body = InstallRequestSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const d = getDb();
    const p = d.profile;
    if (busy(p)) return demoError(409, "setup_busy");
    const ids = body.data.items.filter((id) => p.items.find((x) => x.id === id)?.installable);
    if (!ids.length) return demoError(422, "nothing_selected");
    d.setup.run += 1;
    d.setup.pumping = false;
    p.phase = "installing";
    p.install = { mirror: body.data.mirror, dir: body.data.dir, items: ids };
    for (const x of p.items)
      x.install = ids.includes(x.id) ? { state: "queued", pct: 0, error: null } : null;
    log("info", "mirror", { mirror: body.data.mirror, dir: body.data.dir });
    pump(d);
    return demoJson(p, { status: 202 });
  }),

  http.post<{ id: string }>(v1("/setup/items/:id/retry"), ({ params }) => {
    const item = findItem(params.id);
    if (!item?.install) return demoError(404, "setup_item_not_found", { id: params.id });
    const d = getDb();
    if (item.install.state !== "failed" && item.install.state !== "skipped")
      return demoError(409, "setup_item_state", { id: params.id });
    item.install = { state: "queued", pct: 0, error: null };
    d.profile.phase = "installing";
    log("info", "retry", { item: item.id });
    progress(d.profile, item);
    pump(d);
    return demoJson(d.profile);
  }),

  http.post<{ id: string }>(v1("/setup/items/:id/skip"), ({ params }) => {
    const item = findItem(params.id);
    if (!item?.install) return demoError(404, "setup_item_not_found", { id: params.id });
    if (item.install.state !== "failed" && item.install.state !== "queued")
      return demoError(409, "setup_item_state", { id: params.id });
    item.install.state = "skipped";
    log("info", "skip", { item: item.id });
    progress(getDb().profile, item);
    return demoJson(getDb().profile);
  }),

  /** Demo only: the prototype's 示例机器 switch. There is no backend counterpart. */
  http.post(v1("/demo/setup/machine"), async ({ request }) => {
    const body = DemoMachineSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    const d = getDb();
    d.setup = { machine: body.data.machine, run: d.setup.run + 1, pumping: false, installed: [] };
    d.profile = idleProfile(body.data.machine);
    return demoJson(d.profile);
  }),
];
