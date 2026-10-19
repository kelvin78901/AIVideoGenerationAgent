/** What the setup page shows for an item: the scan result, overridden by the install outcome. */
import { useTranslation } from "react-i18next";

import type { MachineProfile, SetupGroup, SetupItem, SetupPhase } from "@/api/schemas/setup";
import type { Tone } from "@/lib/tone";

export type ShownStatus = SetupItem["status"] | "done" | "fail";

export function shownStatus(x: SetupItem): ShownStatus {
  switch (x.install?.state) {
    case "done":
      return "done";
    case "failed":
      return "fail";
    case "skipped":
      return "skip";
    default:
      return x.status;
  }
}

export const statusTone: Record<ShownStatus, Tone> = {
  checking: "neutral",
  ok: "info",
  done: "info",
  missing: "warn",
  old: "warn",
  warn: "warn",
  fail: "warn",
  optional: "neutral",
  skip: "neutral",
};

/** The summary chips: the install outcome once it is done, the scan result before. */
export function statusCounts(phase: SetupPhase, items: SetupItem[]) {
  const keys: ShownStatus[] =
    phase === "done"
      ? ["done", "fail", "ok", "optional", "skip"]
      : ["ok", "missing", "old", "optional", "warn", "skip"];
  const shown = items.map(shownStatus);
  return keys
    .map((status) => ({ status, n: shown.filter((s) => s === status).length }))
    .filter((c) => c.n > 0);
}

export function overallPct(p: MachineProfile): number {
  if (p.phase === "idle") return 0;
  if (p.phase === "scanning") {
    const seen = p.items.filter((x) => x.status !== "checking").length;
    return p.items.length ? Math.round((seen / p.items.length) * 100) : 0;
  }
  if (p.phase === "installing") {
    const queue = p.items.filter((x) => p.install?.items.includes(x.id));
    const sum = queue.reduce((a, x) => a + (x.install?.pct ?? 0), 0);
    return queue.length ? Math.round(sum / queue.length) : 0;
  }
  return 100;
}

/**
 * Ticked by default after a scan: what is required and can be installed, except changes to the
 * user's own ComfyUI (SPEC 6.4.1: those are only installed when ticked on purpose).
 */
export const requiredIds = (items: SetupItem[]) =>
  items.filter((x) => x.installable && x.required && !x.touches_comfy).map((x) => x.id);

export const installableIds = (items: SetupItem[]) =>
  items.filter((x) => x.installable).map((x) => x.id);

export const GROUPS: SetupGroup[] = ["sys", "rt", "comfy", "w", "svc"];

/** Manifest names come in both languages; pick the one on screen. */
export function useItemName() {
  const { i18n } = useTranslation();
  return (x: SetupItem) => (i18n.language === "en" ? x.name.en : x.name.zh);
}
