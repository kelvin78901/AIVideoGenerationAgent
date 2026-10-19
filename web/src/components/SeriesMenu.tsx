/** The top bar's series title as a menu: every series, then 「新建剧集…」. */
import { Check, ChevronDown, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { useSeriesList } from "@/api/hooks/series";
import type { Series } from "@/api/schemas/series";
import { DEMO_EPISODE, paths } from "@/app/paths";
import { NewSeriesDialog } from "@/components/NewSeriesDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export function SeriesMenu({ current }: { current: Series | undefined }) {
  const { t } = useTranslation();
  const list = useSeriesList();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);

  return (
    <>
      {/* Not modal: a modal menu that opens a dialog leaves `pointer-events: none` on the body. */}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger
          title={t("seriesMenu.label")}
          className="inline-flex min-h-7 items-center gap-1 rounded-md px-1.5 text-topbar-foreground hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:outline-none"
        >
          {current ? t("shell.seriesTitle", { title: current.title }) : t("shell.noSeries")}
          <ChevronDown className="size-3.5 text-topbar-muted" aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          className="max-h-[420px] w-72 max-w-[calc(100vw-24px)] overflow-y-auto p-1.5"
        >
          <DropdownMenuLabel className="px-2 pt-1 pb-1.5 text-xs font-normal text-muted-foreground">
            {t("seriesMenu.heading")}
          </DropdownMenuLabel>
          {(list.data ?? []).map((s) => {
            const active = s.id === current?.id;
            return (
              <DropdownMenuItem
                key={s.id}
                className="min-h-9 gap-2"
                aria-current={active || undefined}
                onSelect={() => void navigate(paths.step(s.id, DEMO_EPISODE, "novel"))}
              >
                <Check className={cn("size-4", !active && "invisible")} aria-hidden />
                <span className="truncate">{t("shell.seriesTitle", { title: s.title })}</span>
              </DropdownMenuItem>
            );
          })}
          {list.isError ? (
            <p className="px-2 py-1.5 text-xs text-destructive">{t("seriesMenu.failed")}</p>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="min-h-9 gap-2" onSelect={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden />
            {t("seriesMenu.new")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <NewSeriesDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}
