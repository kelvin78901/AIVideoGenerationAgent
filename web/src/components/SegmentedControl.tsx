import type { ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
  /** Why the option is disabled (or extra help); shown as a tooltip. */
  hint?: string;
}

/**
 * One-of-N switch (运行位置 本地 / API / 混合, 原文 / 采纳后 / 对比, 图 / 表 …). Always has a
 * value: clicking the selected segment again does not clear it.
 */
export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  label,
  size = "default",
  className,
}: {
  value: T;
  onChange: (value: T) => void;
  options: SegmentOption<T>[];
  /** Accessible name of the group. */
  label: string;
  size?: "default" | "sm";
  className?: string;
}) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(v) => {
        if (v) onChange(v as T);
      }}
      aria-label={label}
      className={className}
    >
      {options.map((o) => {
        const item = (
          <ToggleGroupItem
            key={o.value}
            value={o.value}
            disabled={o.disabled}
            className={cn(size === "sm" && "min-h-7 px-2.5 text-xs")}
          >
            {o.label}
          </ToggleGroupItem>
        );
        if (!o.hint) return item;
        // Disabled buttons swallow pointer events; the wrapper keeps the tooltip working.
        return (
          <Tooltip key={o.value}>
            <TooltipTrigger asChild>
              <span className="flex flex-1 not-first:border-l not-first:border-input [&>button]:w-full [&>button]:border-0">
                {item}
              </span>
            </TooltipTrigger>
            <TooltipContent>{o.hint}</TooltipContent>
          </Tooltip>
        );
      })}
    </ToggleGroup>
  );
}
