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

/** Weighs the overall bar before this machine's download speed was ever measured (bytes/s). */
const WEIGHT_BPS = 20e6;

const finished = (x: SetupItem) =>
  x.install?.state === "done" || x.install?.state === "failed" || x.install?.state === "skipped";

const queueOf = (p: MachineProfile) => p.items.filter((x) => p.install?.items.includes(x.id));

/** What an item downloads: its files' real sizes once known, else the manifest's figure. */
const sizeOf = (x: SetupItem) => x.install?.bytes_total ?? x.size_bytes ?? 0;

/**
 * Size and rough time of installing `items` (SPEC 12.2): downloads at this machine's measured
 * speed, the other steps by rule of thumb (`work_s`). `seconds` is null when there is something
 * to download and no speed to go by.
 */
export function estimate(
  items: SetupItem[],
  bps: number | null,
): { bytes: number; seconds: number | null } {
  const bytes = items.reduce((a, x) => a + (x.size_bytes ?? 0), 0);
  const work = items.reduce((a, x) => a + x.work_s, 0);
  if (bytes > 0 && !bps) return { bytes, seconds: null };
  return { bytes, seconds: work + (bps ? bytes / bps : 0) };
}

/** Seconds an item of the install still needs; null with downloads and no speed to go by. */
function secondsLeft(x: SetupItem, bps: number | null): number | null {
  const inst = x.install;
  if (!inst || finished(x)) return 0;
  const size = sizeOf(x);
  if (inst.state === "running" && size > 0) {
    if (inst.eta_s !== null) return inst.eta_s;
    const left = size - (inst.bytes_done ?? 0);
    if (left <= 0) return 0; // checking the last file
    return bps ? left / bps : null;
  }
  if (inst.state === "running") return x.work_s * (1 - inst.pct / 100);
  if (size > 0 && !bps) return null;
  return x.work_s + (bps ? size / bps : 0);
}

/**
 * Time left of the install that is running: the running download at its own speed, the queued
 * items at that speed too (else the measured one). Null outside an install or without a speed.
 */
export function timeLeft(p: MachineProfile): number | null {
  if (p.phase !== "installing") return null;
  const queue = queueOf(p);
  const live = queue.find((x) => x.install?.state === "running" && x.install.speed)?.install?.speed;
  const bps = live ?? p.download_bps;
  let sum = 0;
  for (const x of queue) {
    const s = secondsLeft(x, bps);
    if (s === null) return null;
    sum += s;
  }
  return sum;
}

/**
 * The summary bar. A scan: items answered. An install: each item weighs its rough time (its
 * download at the measured speed plus its other steps), so a 49 GB download counts for more than
 * a node pack's clone.
 */
export function overallPct(p: MachineProfile): number {
  if (p.phase === "idle") return 0;
  if (p.phase === "scanning") {
    const seen = p.items.filter((x) => x.status !== "checking").length;
    return p.items.length ? Math.round((seen / p.items.length) * 100) : 0;
  }
  if (p.phase === "installing") {
    const bps = p.download_bps ?? WEIGHT_BPS;
    let all = 0;
    let done = 0;
    for (const x of queueOf(p)) {
      const weight = Math.max(1, x.work_s + sizeOf(x) / bps);
      all += weight;
      done += weight * (finished(x) ? 1 : (x.install?.pct ?? 0) / 100);
    }
    return all ? Math.round((done / all) * 100) : 0;
  }
  return 100;
}

/** Sizes (decimal GB / MB, as the manifest and Hugging Face give them), speeds and durations. */
export function useUnits() {
  const { t } = useTranslation("setup");
  const size = (bytes: number) =>
    bytes >= 1e9
      ? t("unit.gb", { n: (bytes / 1e9).toFixed(1) })
      : t("unit.mb", { n: Math.max(1, Math.round(bytes / 1e6)) });
  const speed = (bps: number) => t("unit.mbps", { n: (bps / 1e6).toFixed(1) });
  const duration = (seconds: number) => {
    if (seconds < 60) return t("eta.under1");
    const minutes = Math.ceil(seconds / 60);
    if (minutes < 60) return t("eta.min", { m: minutes });
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m ? t("eta.hourMin", { h, m }) : t("eta.hour", { h });
  };
  /** 「约 5.5 GB，预计 6 分钟」, or the size alone without a speed, or the time alone. */
  const estimateText = ({ bytes, seconds }: { bytes: number; seconds: number | null }) => {
    if (seconds === null) return t("estimate.size", { size: size(bytes) });
    if (bytes === 0) return t("estimate.time", { time: duration(seconds) });
    return t("estimate.sizeTime", { size: size(bytes), time: duration(seconds) });
  };
  return { size, speed, duration, estimateText };
}

/**
 * Ticked by default after a scan: what is required and can be installed, except changes to the
 * user's own ComfyUI (SPEC 6.4.1: those are only installed when ticked on purpose).
 */
export const requiredIds = (items: SetupItem[]) =>
  items.filter((x) => x.installable && x.required && !x.touches_comfy).map((x) => x.id);

/**
 * The left nav's 缺 N 项: required items the scan found missing or outdated and no install has
 * fixed yet. 0 while scanning (items are still checking) and once everything required is there.
 */
export const missingCount = (items: SetupItem[]) =>
  items.filter(
    (x) =>
      x.required && (x.status === "missing" || x.status === "old") && x.install?.state !== "done",
  ).length;

export const installableIds = (items: SetupItem[]) =>
  items.filter((x) => x.installable).map((x) => x.id);

export const GROUPS: SetupGroup[] = ["sys", "rt", "comfy", "w", "svc"];

/** Manifest names come in both languages; pick the one on screen. */
export function useItemName() {
  const { i18n } = useTranslation();
  return (x: SetupItem) => (i18n.language === "en" ? x.name.en : x.name.zh);
}
