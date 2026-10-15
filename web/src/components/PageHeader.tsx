import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/**
 * Page title block from the prototype: eyebrow (「步骤 01 / 06」 or a short note), h1, lead
 * paragraph, and actions on the right (secondary buttons, then the GateButton).
 */
export function PageHeader({
  step,
  eyebrow,
  title,
  lead,
  actions,
  children,
  className,
}: {
  /** Production step number (1–6); renders 「步骤 0N / 06」. */
  step?: number;
  eyebrow?: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const { t } = useTranslation("components");
  return (
    <header className={cn("flex flex-wrap items-start gap-x-6 gap-y-3", className)}>
      <div className="min-w-0 flex-[999_1_28rem]">
        {step != null || eyebrow ? (
          <div className="mb-1 font-mono text-xs text-muted-foreground">
            {step != null
              ? t("pageHeader.step", { n: String(step).padStart(2, "0"), total: "06" })
              : eyebrow}
          </div>
        ) : null}
        <h1 className="text-2xl leading-tight font-bold tracking-tight">{title}</h1>
        {lead ? <p className="mt-1.5 max-w-3xl text-sm text-muted-foreground">{lead}</p> : null}
        {children}
      </div>
      {actions ? (
        <div className="flex flex-[1_1_auto] flex-wrap items-center justify-end gap-2">
          {actions}
        </div>
      ) : null}
    </header>
  );
}
