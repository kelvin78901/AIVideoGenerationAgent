/** Status tones (tokens.css `--tone-*`): meaning only, always paired with text or an icon. */
export type Tone = "pass" | "fail" | "warn" | "info" | "neutral";

export const toneClass: Record<Tone, string> = {
  pass: "bg-tone-pass-bg text-tone-pass-fg border-tone-pass-border",
  fail: "bg-tone-fail-bg text-tone-fail-fg border-tone-fail-border",
  warn: "bg-tone-warn-bg text-tone-warn-fg border-tone-warn-border",
  info: "bg-tone-info-bg text-tone-info-fg border-tone-info-border",
  neutral: "bg-tone-neutral-bg text-tone-neutral-fg border-tone-neutral-border",
};
