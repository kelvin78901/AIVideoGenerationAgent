/**
 * 工作流库 (SPEC 6.4.6; not in the prototype, M0.5 style): ComfyUI workflows registered as local
 * models, by tier, with their health check and last trial. A row opens its bindings, check and
 * trial below it, like the component table above.
 */
import { ChevronDown, FileUp, Stethoscope } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useCheckAllWorkflows, useWorkflows } from "@/api/hooks/workflows";
import type { Workflow, WorkflowTier } from "@/api/schemas/workflows";
import { Chip } from "@/components/Chip";
import { QueryState, Skeleton } from "@/components/QueryState";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ImportWorkflowDialog } from "@/pages/models/ImportWorkflowDialog";
import { WorkflowDetail } from "@/pages/models/WorkflowDetail";
import { tierTone, useCheckText } from "@/pages/models/workflowStatus";

const TIERS: WorkflowTier[] = ["recommended", "mine", "unverified"];
const GRID =
  "grid grid-cols-[minmax(220px,1.6fr)_minmax(120px,1fr)_110px_minmax(170px,1.2fr)_minmax(150px,1fr)_minmax(90px,0.7fr)_28px] items-center gap-3";

function TrialCell({ w }: { w: Workflow }) {
  const { t } = useTranslation("workflows");
  const trial = w.trial;
  if (!trial) return <span className="text-muted-foreground">{t("trialCell.never")}</span>;
  if (trial.status === "running")
    return <span className="text-tone-info-fg">{t("trialCell.running")}</span>;
  const time = formatDateTime(trial.at).slice(5);
  return trial.status === "passed" ? (
    <span>{t("trialCell.passed", { time, seconds: trial.duration_s ?? "—" })}</span>
  ) : (
    <span className="text-tone-fail-fg">{t("trialCell.failed", { time })}</span>
  );
}

function Row({ w, open, onToggle }: { w: Workflow; open: boolean; onToggle: () => void }) {
  const { t } = useTranslation("workflows");
  const { t: te } = useTranslation("enums");
  const checkText = useCheckText();
  const check = checkText(w);
  return (
    <div
      role="rowgroup"
      aria-label={w.name}
      className={cn("border-b border-border/60 last:border-b-0", open && "bg-muted/30")}
    >
      <div
        role="row"
        className={cn(GRID, "min-h-13 cursor-pointer px-3.5 py-2 hover:bg-muted/40")}
        onClick={onToggle}
      >
        <div role="cell" className="flex min-w-0 flex-col gap-0.5">
          <span className="text-sm font-medium">{w.name}</span>
          <span className="truncate font-mono text-[11px] text-muted-foreground">
            {w.model_key}
          </span>
        </div>
        <div role="cell" className="flex flex-wrap gap-1">
          {w.components.map((c) => (
            <span key={c} className="rounded border px-1.5 py-px text-xs">
              {te(`component.${c}` as "component.vid")}
            </span>
          ))}
        </div>
        <div role="cell">
          <StatusBadge tone={tierTone[w.tier]} icon={null}>
            {t(`tier.${w.tier}`)}
          </StatusBadge>
        </div>
        <div role="cell">
          <StatusBadge tone={check.tone}>{check.text}</StatusBadge>
        </div>
        <div role="cell" className="text-[13px]">
          <TrialCell w={w} />
        </div>
        <div
          role="cell"
          className={cn(
            "text-[13px]",
            w.file_changed ? "text-tone-warn-fg" : "text-muted-foreground",
          )}
        >
          {t(w.file_changed ? "file.changed" : "file.same")}
        </div>
        <div role="cell">
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            aria-expanded={open}
            aria-label={t("toggle", { name: w.name })}
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
          >
            <ChevronDown className={cn("transition-transform", open && "rotate-180")} />
          </Button>
        </div>
      </div>
      {open ? <WorkflowDetail w={w} /> : null}
    </div>
  );
}

export function WorkflowLibrary() {
  const { t } = useTranslation("workflows");
  const { t: tc } = useTranslation();
  const list = useWorkflows();
  const checkAll = useCheckAllWorkflows();
  const [tier, setTier] = useState<WorkflowTier | "all">("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const all = list.data ?? [];
  const count = (x: WorkflowTier | "all") =>
    x === "all" ? all.length : all.filter((w) => w.tier === x).length;

  return (
    <section
      aria-labelledby="workflows-title"
      className="flex flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-[1_1_480px] flex-col gap-1">
          <h2 id="workflows-title" className="text-base font-bold">
            {t("title")}
          </h2>
          <p className="text-[13px] leading-relaxed text-muted-foreground">{t("lead")}</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={checkAll.isPending || !all.length}
            onClick={() =>
              checkAll.mutate(undefined, {
                onSuccess: (ws) => toast.success(t("checkedAll", { count: ws.length })),
                onError: (err) => toast.error(errorMessage(tc, err)),
              })
            }
          >
            <Stethoscope aria-hidden />
            {t("checkAll")}
          </Button>
          <Button onClick={() => setImporting(true)}>
            <FileUp aria-hidden />
            {t("import")}
          </Button>
        </div>
      </div>
      <div role="radiogroup" aria-label={t("filter.label")} className="flex flex-wrap gap-1.5">
        {(["all", ...TIERS] as const).map((x) => (
          <Chip key={x} role="radio" selected={tier === x} onClick={() => setTier(x)}>
            {t(`filter.${x}`, { count: count(x) })}
          </Chip>
        ))}
      </div>
      <QueryState query={list} skeleton={<Skeleton className="h-48 w-full" />}>
        {(data) => {
          const rows = data.filter((w) => tier === "all" || w.tier === tier);
          return (
            <div className="overflow-x-auto rounded-lg border">
              <div role="table" aria-label={t("title")} className="min-w-[960px]">
                <div
                  role="row"
                  className={cn(
                    GRID,
                    "border-b bg-muted/50 px-3.5 py-2 text-xs text-muted-foreground",
                  )}
                >
                  {(["name", "components", "tier", "check", "trial", "file"] as const).map((c) => (
                    <div key={c} role="columnheader">
                      {t(`col.${c}`)}
                    </div>
                  ))}
                  <div role="columnheader" />
                </div>
                {rows.length ? (
                  rows.map((w) => (
                    <Row
                      key={w.id}
                      w={w}
                      open={openId === w.id}
                      onToggle={() => setOpenId(openId === w.id ? null : w.id)}
                    />
                  ))
                ) : (
                  <p className="px-3.5 py-6 text-center text-sm text-muted-foreground">
                    {t("empty")}
                  </p>
                )}
              </div>
            </div>
          );
        }}
      </QueryState>
      <ImportWorkflowDialog
        open={importing}
        onOpenChange={setImporting}
        onImported={(w) => {
          setTier("all");
          setOpenId(w.id);
        }}
      />
    </section>
  );
}
