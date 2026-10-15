import { useTranslation } from "react-i18next";

import type { Asset, AssetKind } from "@/api/schemas/assets";
import { Chip } from "@/components/Chip";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";
import { STATUS_TONE } from "@/pages/assets/status";

/** 素材清单: filter by kind, one row per asset with its status. */
export function AssetList({
  assets,
  kinds,
  filter,
  onFilter,
  selectedId,
  onSelect,
}: {
  assets: Asset[];
  kinds: AssetKind[];
  filter: AssetKind | "all";
  onFilter: (f: AssetKind | "all") => void;
  selectedId: string;
  onSelect: (a: Asset) => void;
}) {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const shown = assets.filter((a) => filter === "all" || a.kind === filter);
  return (
    <section
      aria-label={t("list.label")}
      className="flex flex-col gap-2.5 rounded-lg border bg-card p-3"
    >
      <div role="radiogroup" aria-label={t("list.filter")} className="flex flex-wrap gap-1.5">
        {(["all", ...kinds] as const).map((k) => (
          <Chip key={k} role="radio" selected={filter === k} onClick={() => onFilter(k)}>
            {k === "all" ? t("list.all") : te(`assetKind.${k}`)}
          </Chip>
        ))}
      </div>
      <ul className="flex flex-col gap-1">
        {shown.map((a) => {
          const on = a.id === selectedId;
          return (
            <li key={a.id}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onSelect(a)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left outline-none hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring",
                  on ? "border-primary bg-tone-info-bg/40" : "border-transparent",
                )}
              >
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">{a.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {te(`assetKind.${a.kind}`)} ·{" "}
                    {a.shots.length
                      ? t("list.shots", { count: a.shots.length })
                      : t("list.noShots")}
                  </span>
                </span>
                <StatusBadge tone={STATUS_TONE[a.status]} icon={null}>
                  {te(`assetStatus.${a.status}`)}
                </StatusBadge>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
