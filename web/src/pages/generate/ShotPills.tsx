import { useTranslation } from "react-i18next";

import type { Shot } from "@/api/schemas/shots";
import type { TakeStatus } from "@/lib/takes";
import { cn } from "@/lib/utils";

const statusColor: Record<TakeStatus, string> = {
  adopted: "text-tone-info-fg",
  picking: "text-tone-warn-fg",
  running: "text-muted-foreground",
  queued: "text-muted-foreground",
  waiting: "text-muted-foreground",
  not_started: "text-muted-foreground",
};

/** 镜头 pills: every shot with where its takes stand; picks the shot on the wall. */
export function ShotPills({
  shots,
  statusOf,
  selectedId,
  onSelect,
}: {
  shots: Shot[];
  statusOf: (shot: Shot) => TakeStatus;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation("generate");
  return (
    <section aria-label={t("pills.label")} className="flex flex-wrap gap-2">
      {shots.map((s) => {
        const on = s.id === selectedId;
        const status = statusOf(s);
        return (
          <button
            key={s.id}
            type="button"
            aria-pressed={on}
            onClick={() => onSelect(s.id)}
            className={cn(
              "flex min-h-13 min-w-21 flex-col items-start justify-center gap-0.5 rounded-lg border-2 bg-card px-2.5 py-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring",
              on ? "border-primary" : "border-border hover:border-muted-foreground/40",
            )}
          >
            <span className="font-mono text-[13px] font-medium">{s.label}</span>
            <span className={cn("text-[11px] font-medium", statusColor[status])}>
              {t(`status.${status}`)}
            </span>
          </button>
        );
      })}
    </section>
  );
}
