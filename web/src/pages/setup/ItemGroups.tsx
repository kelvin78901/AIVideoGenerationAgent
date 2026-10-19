/** Scan result by group: status, what was found, what to do, tick / install progress. */
import { useTranslation } from "react-i18next";

import type { Message } from "@/api/schemas/common";
import type { SetupItem, SetupPhase } from "@/api/schemas/setup";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { GROUPS, shownStatus, statusTone, useItemName } from "@/pages/setup/items";

export function ItemGroups({
  phase,
  items,
  queue,
  selected,
  onToggle,
  onRetry,
  onSkip,
  pendingId,
}: {
  phase: SetupPhase;
  items: SetupItem[];
  /** Items of the last install request: they show a progress bar instead of a tick. */
  queue: string[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onRetry: (id: string) => void;
  onSkip: (id: string) => void;
  /** Retry / skip in flight. */
  pendingId: string | null;
}) {
  const { t } = useTranslation("setup");
  const nameOf = useItemName();
  const msg = (scope: "found" | "fix" | "error", m: Message) =>
    t(`${scope}.${m.code}` as "found.not_found", { ...m.params, defaultValue: m.code });
  const installing = phase === "installing" || phase === "done";

  return GROUPS.map((g) => {
    const rows = items.filter((x) => x.group === g);
    if (!rows.length) return null;
    return (
      <section
        key={g}
        aria-labelledby={`group-${g}`}
        className="overflow-x-auto rounded-xl border bg-card"
      >
        <div className="min-w-[760px]">
          <div className="flex items-baseline gap-2.5 border-b px-4 py-3">
            <h2 id={`group-${g}`} className="text-[15px] font-bold">
              {t(`group.${g}.name`)}
            </h2>
            <span className="text-xs text-muted-foreground">{t(`group.${g}.hint`)}</span>
          </div>
          <ul>
            {rows.map((x) => {
              const name = nameOf(x);
              const status = shownStatus(x);
              const checking = status === "checking";
              const inst = x.install;
              const failed = inst?.state === "failed";
              const needsAction =
                (x.status === "missing" || x.status === "old") && status !== "done";
              return (
                <li
                  key={x.id}
                  aria-label={name}
                  className="grid min-h-11 grid-cols-[76px_minmax(150px,1.1fr)_minmax(170px,1.4fr)_minmax(170px,1.4fr)_170px] items-center gap-3 border-b border-border/60 px-4 py-2.5 last:border-b-0"
                >
                  <StatusBadge tone={statusTone[status]} icon={null}>
                    {t(`status.${status}`)}
                  </StatusBadge>
                  <span className="flex flex-col gap-0.5">
                    <span className="text-sm font-medium">{name}</span>
                    {x.touches_comfy && x.installable ? (
                      <span className="text-xs text-tone-warn-fg" title={t("touchesComfyTitle")}>
                        {t("touchesComfy")}
                      </span>
                    ) : null}
                  </span>
                  <span className="text-[13px] leading-normal text-muted-foreground">
                    {checking ? "…" : x.found ? msg("found", x.found) : t("none")}
                  </span>
                  <span
                    className={cn(
                      "flex flex-col gap-1.5 text-[13px] leading-normal",
                      needsAction ? "text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {failed && inst.error ? (
                      <span className="text-tone-warn-fg">{msg("error", inst.error)}</span>
                    ) : checking ? null : x.fix ? (
                      msg("fix", x.fix)
                    ) : (
                      t("none")
                    )}
                    {failed ? (
                      <span className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={pendingId === x.id}
                          onClick={() => onRetry(x.id)}
                          aria-label={`${t("retry")} ${name}`}
                        >
                          {t("retry")}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={pendingId === x.id}
                          onClick={() => onSkip(x.id)}
                          aria-label={`${t("skipItem")} ${name}`}
                        >
                          {t("skipItem")}
                        </Button>
                      </span>
                    ) : null}
                  </span>
                  <div className="flex min-w-0 items-center gap-2">
                    {phase === "scanned" && x.installable ? (
                      <label className="flex items-center gap-2 text-[13px]">
                        <Checkbox
                          checked={selected.has(x.id)}
                          onCheckedChange={() => onToggle(x.id)}
                          aria-label={`${x.required ? t("pick") : t("pickOptional")} ${name}`}
                        />
                        {x.required ? t("pick") : t("pickOptional")}
                      </label>
                    ) : null}
                    {installing && inst && queue.includes(x.id) ? (
                      <>
                        <Progress
                          value={inst.pct}
                          aria-label={t("progressOf", { name })}
                          className="flex-1 bg-muted"
                          indicatorClassName={cn(failed && "bg-status-warn")}
                        />
                        <span
                          className={cn(
                            "shrink-0 font-mono text-xs",
                            failed ? "text-tone-warn-fg" : "text-muted-foreground",
                          )}
                        >
                          {failed ? t("status.fail") : `${inst.pct}%`}
                        </span>
                      </>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </section>
    );
  });
}
