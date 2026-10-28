import { useTranslation } from "react-i18next";

import type { GenerateLogEntry } from "@/api/schemas/generate";
import { formatTime, formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 运行记录, newest first. Model keys and costs in the params are formatted here. */
export function RunLog({
  entries,
  modelName,
}: {
  entries: GenerateLogEntry[];
  modelName: (key: string | null | undefined) => string;
}) {
  const { t } = useTranslation("generate");
  const { t: te } = useTranslation("enums");
  // The backend lists them oldest first; within the same minute too (a fallback before its take).
  const lines = entries
    .map((e, i) => ({ e, i }))
    .sort((a, b) => b.e.at.localeCompare(a.e.at) || b.i - a.i)
    .map(({ e }) => e);

  const text = (e: GenerateLogEntry) => {
    const p = e.message.params;
    const cost = typeof p.cost_usd === "number" && p.cost_usd > 0 ? p.cost_usd : null;
    const issues = typeof p.issues === "string" ? p.issues.split(",").filter(Boolean) : [];
    return t(`log.${e.message.code}` as "log.started", {
      ...p,
      model: modelName(typeof p.model === "string" ? p.model : null),
      cost: cost === null ? "" : t("log.cost", { amount: formatUsd(cost, { cents: true }) }),
      issues: issues
        .map((c) => te(`qaIssue.${c}` as "qaIssue.face_mismatch"))
        .join(t("log.issueSep")),
      defaultValue: e.message.code,
    });
  };

  return (
    <section
      aria-labelledby="run-log-title"
      className="flex min-w-0 flex-1 basis-80 flex-col gap-2.5 rounded-xl border bg-card p-4"
    >
      <h2 id="run-log-title" className="text-base font-bold">
        {t("log.title")}
      </h2>
      {lines.length ? (
        <ol className="flex flex-col">
          {lines.map((e) => (
            <li
              key={e.id}
              className="flex gap-2.5 border-b py-1.5 text-[13px] leading-relaxed last:border-b-0"
            >
              <span className="shrink-0 font-mono text-xs text-muted-foreground">
                {formatTime(e.at)}
              </span>
              <span className="shrink-0 font-mono text-xs">{e.shot_label}</span>
              <span className={cn(e.warn && "text-tone-warn-fg")}>{text(e)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground">{t("log.empty")}</p>
      )}
    </section>
  );
}
