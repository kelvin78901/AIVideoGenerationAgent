import { AlertTriangle, Check, X, type LucideIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { toneClass, type Tone } from "@/lib/tone";
import { cn } from "@/lib/utils";

export type { Tone };

/** Pass / fail always carry an icon besides colour (SPEC 11.3: status colour never alone). */
const defaultIcon: Partial<Record<Tone, LucideIcon>> = {
  pass: Check,
  fail: X,
  warn: AlertTriangle,
};

/** Small status pill: 已采纳 / 草稿 / 通过 / 未过 / 待更新 … The text comes from the caller. */
export function StatusBadge({
  tone = "neutral",
  icon,
  children,
  className,
  ...rest
}: {
  tone?: Tone;
  /** `null` hides the default icon (e.g. a neutral count); a component overrides it. */
  icon?: LucideIcon | null;
  children: ReactNode;
  className?: string;
} & Omit<ComponentProps<"span">, "children">) {
  const Icon = icon === null ? null : (icon ?? defaultIcon[tone] ?? null);
  return (
    <span
      className={cn(
        "inline-flex w-fit shrink-0 items-center gap-1 rounded border px-1.5 py-px text-xs font-medium whitespace-nowrap",
        toneClass[tone],
        className,
      )}
      {...rest}
    >
      {Icon ? <Icon className="size-3" aria-hidden /> : null}
      {children}
    </span>
  );
}
