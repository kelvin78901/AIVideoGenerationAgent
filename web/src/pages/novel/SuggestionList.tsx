import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ApiError, errorMessage } from "@/api/client";
import {
  useAcceptAllSuggestions,
  useSuggestionAction,
  type SuggestionAction,
} from "@/api/hooks/novel";
import type { ModelOption } from "@/api/schemas/models";
import type { Suggestion } from "@/api/schemas/novel";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label, Textarea } from "@/components/ui/form";
import { cn } from "@/lib/utils";
import { modelName } from "@/lib/versions";

function SuggestionCard({
  s,
  seriesId,
  models,
  onFocus,
}: {
  s: Suggestion;
  seriesId: string;
  models: readonly ModelOption[];
  onFocus: (para: number) => void;
}) {
  const { t } = useTranslation("novel");
  const { t: te } = useTranslation("enums");
  const { t: tc } = useTranslation();
  const ids = useId();
  const act = useSuggestionAction(seriesId);
  const [editing, setEditing] = useState(false);
  const [instruction, setInstruction] = useState("");
  // A rewrite over the per-call cap waits here for the user's yes (hard rule 6).
  const [overBudget, setOverBudget] = useState<ApiError | null>(null);
  const accepted = s.status === "accepted";
  const ignored = s.status === "rejected";
  const para = s.para_idx + 1;

  const run = (a: SuggestionAction, done?: (updated: Suggestion) => void) =>
    act.mutate(a, {
      onSuccess: done,
      onError: (err) => {
        if (err instanceof ApiError && err.code === "over_budget") setOverBudget(err);
        else toast.error(errorMessage(tc, err));
      },
    });

  const rewrite = (confirmBudget: boolean) => {
    setOverBudget(null);
    run({ id: s.id, action: "rewrite", instruction, confirm_budget: confirmBudget }, (updated) => {
      setEditing(false);
      setInstruction("");
      onFocus(s.para_idx);
      toast.success(
        t("suggestions.rewriteDone", {
          n: para,
          model: modelName(models, updated.rewritten_by),
        }),
      );
    });
  };

  return (
    <article
      aria-label={t("suggestions.para", { n: para })}
      className={cn(
        "flex flex-col gap-2.5 rounded-lg border bg-card p-3.5",
        accepted && "border-primary",
        ignored && "bg-muted/60",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge icon={null}>{te(`suggestionKind.${s.kind}`)}</StatusBadge>
        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => onFocus(s.para_idx)}>
          {t("suggestions.para", { n: para })}
        </Button>
        {s.rewrite_instruction !== null ? (
          <StatusBadge tone="info" icon={null}>
            {t("suggestions.rewritten")}
          </StatusBadge>
        ) : null}
        <span
          className={cn(
            "ml-auto text-xs font-medium",
            accepted
              ? "text-tone-info-fg"
              : ignored
                ? "text-muted-foreground"
                : "text-tone-warn-fg",
          )}
        >
          {t(`suggestions.status.${s.status}`)}
        </span>
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">{s.reason}</p>
      <blockquote
        className={cn(
          "rounded-md bg-muted px-3 py-2.5 text-[15px] leading-7",
          ignored && "text-muted-foreground line-through",
        )}
      >
        {s.text}
      </blockquote>
      {editing ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${ids}-rw`} className="text-xs">
            {t("suggestions.rewriteLabel")}
          </Label>
          <Textarea
            id={`${ids}-rw`}
            rows={2}
            value={instruction}
            placeholder={t("suggestions.rewritePlaceholder")}
            onChange={(e) => setInstruction(e.target.value)}
          />
          {overBudget ? (
            <div
              role="alert"
              className="flex flex-wrap items-center gap-2 rounded-md bg-tone-warn-bg px-3 py-2 text-sm text-tone-warn-fg"
            >
              <span>{errorMessage(tc, overBudget)}</span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={act.isPending}
                onClick={() => rewrite(true)}
              >
                {t("suggestions.rewriteAnyway")}
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              className="self-end"
              disabled={!instruction.trim() || act.isPending}
              onClick={() => rewrite(false)}
            >
              {t("suggestions.rewriteSubmit")}
            </Button>
          )}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={accepted ? "outline" : "default"}
          disabled={act.isPending}
          onClick={() =>
            run({ id: s.id, action: accepted ? "reset" : "accept" }, () => onFocus(s.para_idx))
          }
        >
          {t(accepted ? "suggestions.unaccept" : "suggestions.accept")}
        </Button>
        <Button
          variant="outline"
          aria-expanded={editing}
          onClick={() => {
            setEditing(!editing);
            setInstruction("");
            setOverBudget(null);
          }}
        >
          {t(editing ? "suggestions.collapse" : "suggestions.rewrite")}
        </Button>
        <Button
          variant="outline"
          disabled={act.isPending}
          onClick={() => run({ id: s.id, action: ignored ? "reset" : "reject" })}
        >
          {t(ignored ? "suggestions.restore" : "suggestions.ignore")}
        </Button>
      </div>
    </article>
  );
}

/**
 * 补全建议: decide on each addition; nothing reaches the text without 「采纳」. `adopted` false: the
 * 小说补全 version on screen is not the adopted one (the bible still reads the adopted one).
 */
export function SuggestionList({
  seriesId,
  suggestions,
  adopted = true,
  models,
  onFocus,
}: {
  seriesId: string;
  suggestions: Suggestion[];
  adopted?: boolean;
  models: readonly ModelOption[];
  onFocus: (para: number) => void;
}) {
  const { t } = useTranslation("novel");
  const { t: tc } = useTranslation();
  const acceptAll = useAcceptAllSuggestions(seriesId);
  const accepted = suggestions.filter((s) => s.status === "accepted").length;
  return (
    <section aria-labelledby="novel-suggestions" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 id="novel-suggestions" className="text-base font-bold">
          {t("suggestions.title")}
        </h2>
        <span className="text-xs text-muted-foreground tabular-nums">
          {t("suggestions.count", { accepted, total: suggestions.length })}
        </span>
        {adopted ? null : <Badge variant="warn">{t("suggestions.unadopted")}</Badge>}
        <Button
          variant="outline"
          className="ml-auto"
          disabled={acceptAll.isPending || suggestions.length === 0}
          onClick={() =>
            acceptAll.mutate(undefined, {
              onSuccess: () => toast.success(t("suggestions.acceptAllDone")),
              onError: (err) => toast.error(errorMessage(tc, err)),
            })
          }
        >
          {t("suggestions.acceptAll")}
        </Button>
      </div>
      {adopted ? null : (
        <p className="text-xs text-muted-foreground">{t("suggestions.unadoptedHint")}</p>
      )}
      {suggestions.length === 0 ? <EmptyState title={t("suggestions.empty")} /> : null}
      {suggestions.map((s) => (
        <SuggestionCard key={s.id} s={s} seriesId={seriesId} models={models} onFocus={onFocus} />
      ))}
    </section>
  );
}
