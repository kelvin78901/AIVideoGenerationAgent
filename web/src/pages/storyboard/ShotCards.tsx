import { useTranslation } from "react-i18next";

import type { Shot } from "@/api/schemas/shots";
import type { Aspect } from "@/api/schemas/spec";
import { MediaThumb } from "@/components/MediaThumb";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";

/** 镜头列表: one card per shot; landscape specs get wider cards (SPEC 16.4). */
export function ShotCards({
  shots,
  aspect,
  selectedId,
  onSelect,
}: {
  shots: Shot[];
  aspect: Aspect;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation("storyboard");
  const { t: te } = useTranslation("enums");
  const wide = aspect === "16:9" || aspect === "21:9";
  return (
    <section
      aria-label={t("cards.label")}
      className={cn(
        "grid gap-2.5",
        wide ? "grid-cols-2 md:grid-cols-3" : "grid-cols-3 md:grid-cols-5 2xl:grid-cols-9",
      )}
    >
      {shots.map((s) => {
        const on = s.id === selectedId;
        return (
          <button
            key={s.id}
            type="button"
            aria-pressed={on}
            onClick={() => onSelect(s.id)}
            className={cn(
              "flex flex-col gap-1.5 rounded-lg border-2 bg-card p-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring",
              on ? "border-primary" : "border-transparent hover:border-border",
            )}
          >
            <MediaThumb aspect={aspect} seed={s.label} label={s.label} caption={s.summary} />
            <span className="flex items-center gap-1">
              <span className="font-mono text-xs font-medium">{s.label}</span>
              <StatusBadge
                tone={s.confirmed && !s.confirm_stale ? "info" : "warn"}
                icon={null}
                className="ml-auto"
              >
                {t(
                  s.confirm_stale
                    ? "status.stale"
                    : s.confirmed
                      ? "status.confirmed"
                      : "status.draft",
                )}
              </StatusBadge>
            </span>
            <span className="text-xs">{te(`shotType.${s.shot_type}`)}</span>
            <span className="text-xs text-muted-foreground">
              {t("cards.meta", { framing: te(`framing.${s.framing}`), seconds: s.duration_s })}
            </span>
          </button>
        );
      })}
    </section>
  );
}
