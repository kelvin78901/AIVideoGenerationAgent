/**
 * Server events (SPEC 9): one dispatcher for everything that arrives over SSE and for events
 * injected locally (the MSW demo data simulates runs and installs this way), so pages react
 * the same whether the backend or the demo produced the event.
 */
import type { QueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { toast } from "sonner";

import { productKeys } from "@/api/hooks/products";
import { callKeys, upsertJob } from "@/api/hooks/useJobs";
import { JobSchema } from "@/api/schemas/jobs";

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
  // Products feed series-level views (episode script status, suggestions, bible).
  "product.updated": [productKeys.all, ["series"]],
  "version.created": [productKeys.all],
};

export function dispatchEvent(client: QueryClient, t: TFunction, type: EventType, data: unknown) {
  if (type === "job.updated") {
    const job = JobSchema.safeParse(data);
    if (job.success) upsertJob(client, job.data);
    else console.error("[events] bad job.updated payload", job.error);
  } else if (type === "toast") {
    const ev = data as ToastEvent;
    const text = t(`toast.${ev.code}` as "toast.generic", {
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
