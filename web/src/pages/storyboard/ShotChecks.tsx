import { AlertTriangle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useRunShotChecks, useShotChecks } from "@/api/hooks/shots";
import type { ShotIssue } from "@/api/schemas/shots";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";

/** One finding in words: a rule's from its code (and params), the model's as it said it. */
export function IssueText({ issue }: { issue: ShotIssue }) {
  const { t } = useTranslation("storyboard");
  if (issue.source === "llm") return <>{issue.text}</>;
  return (
    <>
      {t(`checks.code.${issue.code}` as "checks.code.undone", {
        ...issue.params,
        defaultValue: issue.code,
      })}
    </>
  );
}

function Source({ issue }: { issue: ShotIssue }) {
  const { t } = useTranslation("storyboard");
  return (
    <StatusBadge tone="neutral" icon={null} className="ml-1">
      {t(issue.source === "rule" ? "checks.rule" : "checks.model")}
    </StatusBadge>
  );
}

/** 分镜检查 above the shot list (M5.5, sketch S1): every finding, rules now and the model's last
 * check, and 「检查」 / 「重新检查」. Only a warning: confirming goes on. */
export function ShotChecksBanner({ episodeId }: { episodeId: string }) {
  const { t } = useTranslation("storyboard");
  const checks = useShotChecks(episodeId);
  const run = useRunShotChecks(episodeId);
  if (!checks.data) return null;
  const { issues, llm_state: state } = checks.data;
  const running = state === "running" || run.isPending;
  const button = (
    <Button size="sm" variant="outline" disabled={running} onClick={() => run.mutate()}>
      <RefreshCw aria-hidden className={running ? "animate-spin" : undefined} />
      {t(state === "none" ? "checks.run" : "checks.rerun")}
    </Button>
  );
  if (!issues.length)
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        {t(state === "ready" ? "checks.clean" : "checks.cleanRules")}
        {state === "ready" ? null : button}
      </div>
    );
  return (
    <section
      aria-label={t("checks.label")}
      className="flex flex-col gap-1.5 rounded-md border border-tone-warn-border bg-tone-warn-bg p-3 text-sm text-tone-warn-fg"
    >
      <div className="flex flex-wrap items-center gap-2">
        <AlertTriangle aria-hidden className="size-4" />
        <span className="font-bold">{t("checks.title", { count: issues.length })}</span>
        <span>{t("checks.onlyWarn")}</span>
        {state === "stale" ? <span>{t("checks.stale")}</span> : null}
        <span className="ml-auto">{button}</span>
      </div>
      <ul className="flex list-disc flex-col gap-0.5 pl-5">
        {issues.map((i, n) => (
          <li key={`${i.shot_id}-${i.code}-${n}`}>
            <span className="font-mono font-medium">{i.label}</span> <IssueText issue={i} />
            <Source issue={i} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The findings about one shot, at the top of its settings (sketch S2). */
export function ShotIssues({ episodeId, shotId }: { episodeId: string; shotId: string }) {
  const { t } = useTranslation("storyboard");
  const checks = useShotChecks(episodeId);
  const mine = (checks.data?.issues ?? []).filter((i) => i.shot_id === shotId);
  if (!mine.length) return null;
  return (
    <div
      role="note"
      aria-label={t("checks.shotLabel")}
      className="rounded-md border border-tone-warn-border bg-tone-warn-bg p-2.5 text-sm text-tone-warn-fg"
    >
      {t("checks.shotTitle", { count: mine.length })}
      <ul className="mt-1 list-disc pl-5">
        {mine.map((i, n) => (
          <li key={`${i.code}-${n}`}>
            <IssueText issue={i} />
            <Source issue={i} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A candidate's check (M5.5 关键帧检查 / take 检查): one line per item, ✓ or ✗ and why. */
export function CheckLines({
  items,
}: {
  items: { check: string; ok: boolean; note: string; frame?: number | null }[];
}) {
  const { t } = useTranslation("storyboard");
  if (!items.length) return null;
  return (
    <ul aria-label={t("checks.itemsLabel")} className="flex flex-col gap-0.5 text-xs">
      {items.map((x, n) => (
        <li key={`${x.check}-${n}`} className={x.ok ? "text-status-pass" : "text-status-fail"}>
          {x.ok ? "✓ " : "✗ "}
          {t(`checks.item.${x.check}` as "checks.item.start", { defaultValue: x.check })}
          {!x.ok && x.frame ? ` · ${t("checks.frame", { n: x.frame })}` : ""}
          {!x.ok && x.note ? `：${x.note}` : ""}
        </li>
      ))}
    </ul>
  );
}
