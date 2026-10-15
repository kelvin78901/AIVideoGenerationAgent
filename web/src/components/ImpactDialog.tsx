import { AlertTriangle } from "lucide-react";
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useApplyImpact } from "@/api/hooks/impact";
import type { Impact, ImpactAction, ApplyImpactResult } from "@/api/schemas/impact";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";

type Labels = Partial<Record<ImpactAction, string>>;

function ImpactBody({
  impact,
  labels,
  onResolved,
}: {
  impact: Impact;
  labels?: Labels;
  onResolved?: (action: ImpactAction, result: ApplyImpactResult) => void;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const apply = useApplyImpact();
  const cost = formatUsd(impact.rerun_cost_usd, { cents: true });
  const done: Record<ImpactAction, string> = {
    mark: t("impact.marked"),
    rerun: t("impact.rerunQueued", { cost }),
    undo: t("impact.undone"),
  };
  const run = (action: ImpactAction) =>
    apply.mutate(
      { impact_id: impact.id, action },
      {
        onSuccess: (result) => {
          toast.success(done[action]);
          onResolved?.(action, result);
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );

  return (
    <>
      <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
        {impact.lines.map((line, i) => (
          <li key={i}>
            {t(`impact.line.${line.code}` as "impact.line.keyframes", {
              ...line.params,
              defaultValue: line.code,
            })}
            {line.cost_usd !== null
              ? ` · ${t("impact.lineCost", { cost: formatUsd(line.cost_usd, { cents: true }) })}`
              : ""}
            {line.optional ? t("impact.optional") : ""}
          </li>
        ))}
      </ul>
      {impact.unaffected ? (
        <p className="text-sm text-muted-foreground">
          {t(`impact.unaffected.${impact.unaffected.code}` as "impact.unaffected.unaffected_spec", {
            ...impact.unaffected.params,
            defaultValue: impact.unaffected.code,
          })}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button disabled={apply.isPending} onClick={() => run("mark")}>
          {labels?.mark ?? t("impact.mark")}
        </Button>
        <Button
          variant="outline"
          className="border-tone-warn-border text-tone-warn-fg"
          disabled={apply.isPending}
          onClick={() => run("rerun")}
        >
          {labels?.rerun ?? t("impact.rerun", { cost })}
        </Button>
        <Button variant="outline" disabled={apply.isPending} onClick={() => run("undo")}>
          {labels?.undo ?? t("impact.undo")}
        </Button>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{t("impact.footer")}</p>
    </>
  );
}

/**
 * Shown when a change hits confirmed upstream work (SPEC 16.2): what becomes outdated and what
 * redoing it costs, with 只标记待更新 / 自动重跑 / 撤销. `inline` sits in the page (script and
 * spec pages, as in the prototype); `modal` is a dialog (asset lock / unlock).
 */
export function ImpactDialog({
  impact,
  title,
  detail,
  variant = "inline",
  open = true,
  onOpenChange,
  labels,
  onResolved,
  className,
}: {
  impact: Impact;
  title: ReactNode;
  /** What changed, under the title (「改的是：……」). */
  detail?: ReactNode;
  variant?: "inline" | "modal";
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Page wording, e.g. 成片规格「改，并标记待更新」. */
  labels?: Labels;
  /** After the action succeeded; on `undo` the page reverts its edit. */
  onResolved?: (action: ImpactAction, result: ApplyImpactResult) => void;
  className?: string;
}) {
  const titleId = useId();
  if (variant === "modal")
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent role="alertdialog" className={cn("gap-3", className)}>
          <DialogTitle className="flex items-center gap-2 text-base font-bold">
            <AlertTriangle className="size-4 text-tone-warn-fg" aria-hidden />
            {title}
          </DialogTitle>
          <DialogDescription className={detail ? "text-sm" : "sr-only"}>
            {detail ?? title}
          </DialogDescription>
          <ImpactBody
            impact={impact}
            labels={labels}
            onResolved={(action, result) => {
              onOpenChange?.(false);
              onResolved?.(action, result);
            }}
          />
        </DialogContent>
      </Dialog>
    );
  if (!open) return null;
  return (
    <section
      role="alertdialog"
      aria-labelledby={titleId}
      className={cn(
        "flex flex-col gap-2.5 rounded-lg border border-tone-warn-border bg-tone-warn-bg p-4",
        className,
      )}
    >
      <h2 id={titleId} className="flex items-center gap-2 text-base font-bold">
        <AlertTriangle className="size-4 text-tone-warn-fg" aria-hidden />
        {title}
      </h2>
      {detail ? <div className="text-sm">{detail}</div> : null}
      <ImpactBody impact={impact} labels={labels} onResolved={onResolved} />
    </section>
  );
}
