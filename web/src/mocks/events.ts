/** Demo events: handlers push simulated server events through the app's own dispatcher. */
import { injectEvent, type EventType } from "@/api/events";

/** Simulated durations; tests shorten them. */
export const demoTiming = {
  /** `POST /products/{id}/run` appends the new version after this long (prototype: 1.4 s). */
  runMs: 1400,
  /** 「重写这一段」 (prototype: 1.1 s). */
  rewriteMs: 1100,
  /** First-run scan: one item per tick (prototype: 110 ms). */
  setupScanMs: 110,
  /** Install: one progress step per tick (prototype: 120 ms; +10 % for downloads, +34 % otherwise). */
  setupTickMs: 120,
};

export function emitDemoEvent(type: EventType, data: unknown, delayMs = 0): void {
  if (delayMs <= 0) injectEvent(type, data);
  else setTimeout(() => injectEvent(type, data), delayMs);
}
