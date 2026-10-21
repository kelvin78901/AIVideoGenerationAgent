/**
 * Server events (SPEC 9): one dispatcher for everything that arrives over SSE and for events
 * injected locally (the MSW demo data simulates runs and installs this way), so pages react
 * the same whether the backend or the demo produced the event.
 */
import type { QueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { toast } from "sonner";

import { generateKeys } from "@/api/hooks/generate";
import { productKeys } from "@/api/hooks/products";
import { applySetupProgress } from "@/api/hooks/setup";
import { applySyncUpdate } from "@/api/hooks/sync";
import { callKeys, upsertJob } from "@/api/hooks/useJobs";
import { JobSchema } from "@/api/schemas/jobs";
import { SetupProgressSchema } from "@/api/schemas/setup";
import { SyncRunSchema } from "@/api/schemas/sync";

export const EVENT_TYPES = [
  "job.updated",
  "product.updated",
  "version.created",
  "cost.updated",
  "gate.updated",
  "sync.updated",
  "setup.progress",
  "setup.log",
  "toast",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

interface ToastEvent {
  level?: "success" | "info" | "warning" | "error";
  code: string;
  params?: Record<string, unknown>;
}

type Listener = (data: unknown) => void;
const listeners = new Map<EventType, Set<Listener>>();

/** Page-level subscription (e.g. the setup log). Returns the unsubscribe function. */
export function onEvent(type: EventType, fn: Listener): () => void {
  let set = listeners.get(type);
  if (!set) listeners.set(type, (set = new Set()));
  set.add(fn);
  return () => set.delete(fn);
}

/** Cache keys refetched when an event of that type arrives. Extended as resources are added. */
const invalidates: Partial<Record<EventType, readonly (readonly unknown[])[]>> = {
  "cost.updated": [callKeys.all],
  // Products feed series-level views (episode script status, suggestions, bible) and episode
  // ones (the script, the step badges).
  "product.updated": [productKeys.all, ["series"], ["episodes"]],
  // A new take also adds a line to the generate step's run log.
  "version.created": [productKeys.all, generateKeys.logs],
  // Confirming or reopening locks products and changes the step badges and script status.
  "gate.updated": [productKeys.all, ["series"], ["episodes"]],
};

export function dispatchEvent(client: QueryClient, t: TFunction, type: EventType, data: unknown) {
  if (type === "job.updated") {
    const job = JobSchema.safeParse(data);
    if (job.success) upsertJob(client, job.data);
    else console.error("[events] bad job.updated payload", job.error);
  } else if (type === "setup.progress") {
    const ev = SetupProgressSchema.safeParse(data);
    if (ev.success) applySetupProgress(client, ev.data);
    else console.error("[events] bad setup.progress payload", ev.error);
  } else if (type === "sync.updated") {
    const ev = SyncRunSchema.safeParse(data);
    if (ev.success) applySyncUpdate(client, ev.data);
    else console.error("[events] bad sync.updated payload", ev.error);
  } else if (type === "toast") {
    const ev = data as ToastEvent;
    // 确认并同步 finished: the wording says how many failed, when some did.
    const code =
      ev.code === "cascade_done" && Number(ev.params?.failed) > 0 ? "cascade_done_failed" : ev.code;
    const text = t(`toast.${code}` as "toast.generic", {
      ...ev.params,
      code: ev.code,
      defaultValue: t("toast.generic", { code: ev.code }),
    });
    toast[ev.level ?? "info"](text);
  }
  for (const queryKey of invalidates[type] ?? []) void client.invalidateQueries({ queryKey });
  for (const fn of listeners.get(type) ?? []) fn(data);
}

type Sink = (type: EventType, data: unknown) => void;
const sinks = new Set<Sink>();

/** Deliver an event that did not come over SSE (MSW demo data). */
export function injectEvent(type: EventType, data: unknown): void {
  for (const sink of sinks) sink(type, data);
}

/** Used by `useEventStream` to route injected events into `dispatchEvent`. */
export function onInjectedEvent(sink: Sink): () => void {
  sinks.add(sink);
  return () => sinks.delete(sink);
}
