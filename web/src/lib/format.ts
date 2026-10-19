/** Number formatting shared by every page. Money is always USD ("$8.94", "$15"). */

/** "$8.94"; whole amounts drop the cents ("$15") unless `cents` is set. */
export function formatUsd(value: number, { cents = false }: { cents?: boolean } = {}): string {
  return formatMoney(value, "USD", { cents });
}

/** Like `formatUsd`, for list prices that providers quote in CNY ("¥6"). */
export function formatMoney(
  value: number,
  currency: "USD" | "CNY",
  { cents = false }: { cents?: boolean } = {},
): string {
  const whole = Number.isInteger(value) && !cents;
  const digits = value.toLocaleString("en-US", {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  });
  return `${currency === "CNY" ? "¥" : "$"}${digits}`;
}

const pad2 = (n: number) => String(n).padStart(2, "0");

/** Wall-clock time of an ISO timestamp in the viewer's time zone: "09:41". */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** Day and time of an ISO timestamp in the viewer's time zone: "2026-10-18 09:41". */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${formatTime(iso)}`;
}

/** File size, binary units as Windows shows them: 6938078334 → "6.5 GB", 228456789 → "218 MB". */
export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  for (; value >= 1024 && i < units.length - 1; i += 1) value /= 1024;
  const digits = i === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits).replace(/\.0$/, "")} ${units[i]}`;
}

/** Seconds as a clock: 34 → "0:34", 70 → "1:10", 11.5 → "0:11". */
export function formatClock(seconds: number, { pad = false }: { pad?: boolean } = {}): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  return `${pad ? String(m).padStart(2, "0") : m}:${String(s % 60).padStart(2, "0")}`;
}

/** 0.976 → "97.6%"; integers keep no decimals (1 → "100%"). */
export function formatPercent(ratio: number, digits = 1): string {
  const pct = ratio * 100;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(digits)}%`;
}

/** "9:16 · 1080×1920 · 24 fps" (the top-bar spec tag). */
export function formatSpecTag(aspect: string, w: number, h: number, fps: number): string {
  return `${aspect} · ${w}×${h} · ${fps} fps`;
}
