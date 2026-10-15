import { Check } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Toggle chip (兜底条件、景别、字体风格 …). `selected` drives aria-pressed, or aria-checked
 * when used as a radio inside `role="radiogroup"`.
 */
export function Chip({
  selected = false,
  check = false,
  role,
  className,
  children,
  ...props
}: React.ComponentProps<"button"> & {
  selected?: boolean;
  /** Prefix a check mark when selected (multi-select chips). */
  check?: boolean;
  role?: "radio";
}) {
  return (
    <button
      type="button"
      role={role}
      aria-pressed={role ? undefined : selected}
      aria-checked={role ? selected : undefined}
      className={cn(
        "inline-flex min-h-7 items-center gap-1 rounded-md border bg-card px-2.5 text-xs whitespace-nowrap outline-none hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        selected &&
          (check
            ? "border-tone-info-border bg-tone-info-bg text-tone-info-fg hover:bg-tone-info-bg"
            : "border-foreground bg-foreground text-background hover:bg-foreground"),
        className,
      )}
      {...props}
    >
      {check && selected ? <Check className="size-3" aria-hidden /> : null}
      {children}
    </button>
  );
}
