/** Demo events: handlers push simulated server events through the app's own dispatcher. */
import { injectEvent, type EventType } from "@/api/events";

/**
 * Simulated durations. Tests set the step timings (`setup*Ms`, `syncTickMs`) to 0: every step then
 * runs in one task and the page renders the end state once (see `repeatDemo`).
 */
export const demoTiming = {
  /** `POST /products/{id}/run` appends the new version after this long (prototype: 1.4 s). */
  runMs: 1400,
  /** 「重写这一段」 (prototype: 1.1 s). */
  rewriteMs: 1100,
  /** First-run scan: one item per tick (prototype: 110 ms). */
  setupScanMs: 110,
  /** Install: one progress step per tick (prototype: 120 ms; +10 % for downloads, +34 % otherwise). */
  setupTickMs: 120,
  /** 「立即同步」: one file per tick (prototype: 90 ms, 24 files). */
  syncTickMs: 90,
};

/** Upper bound for one zero-delay run, so a step that never returns false cannot hang a test. */
const MAX_STEPS = 10_000;

/**
 * Calls `step` every `ms` until it returns false or `alive()` turns false. With `ms <= 0` all steps
 * run back to back in the next task: the events still arrive in order, but React renders once
 * instead of once per step (a full install is ~120 steps).
 */
export function repeatDemo(ms: number, step: () => boolean, alive: () => boolean = () => true) {
  if (ms <= 0) {
    setTimeout(() => {
      for (let i = 0; i < MAX_STEPS && alive() && step(); i += 1);
    }, 0);
    return;
  }
  const timer = setInterval(() => {
    if (!alive() || !step()) clearInterval(timer);
  }, ms);
}

export function emitDemoEvent(type: EventType, data: unknown, delayMs = 0): void {
  if (delayMs <= 0) injectEvent(type, data);
  else setTimeout(() => injectEvent(type, data), delayMs);
}
