/** Demo events: handlers push simulated server events through the app's own dispatcher. */
import { injectEvent, type EventType } from "@/api/events";

export function emitDemoEvent(type: EventType, data: unknown, delayMs = 0): void {
  if (delayMs <= 0) injectEvent(type, data);
  else setTimeout(() => injectEvent(type, data), delayMs);
}
