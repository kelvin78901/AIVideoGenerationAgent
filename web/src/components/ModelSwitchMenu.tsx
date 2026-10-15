import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { ModelOption } from "@/api/schemas/models";
import { paths } from "@/app/paths";
import { CostBadge } from "@/components/CostBadge";
import { StatusBadge } from "@/components/StatusBadge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/**
 * 「不满意换一个」 menu (SPEC 7.4), shared by RunBar and the Inspector: every model of the
 * component except the current one, in fallback order; picking one reruns with it.
 */
export function ModelSwitchMenu({
  options,
  currentKey,
  onPick,
  children,
  side = "bottom",
  align = "end",
}: {
  /** Already in the component's `alt_order`. */
  options: readonly ModelOption[];
  currentKey?: string | null;
  onPick: (key: string) => void;
  /** The trigger button. */
  children: ReactNode;
  side?: "top" | "bottom";
  align?: "start" | "end";
}) {
  const { t } = useTranslation("components");
  const { t: te } = useTranslation("enums");
  const others = options.filter((m) => m.key !== currentKey);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
      <DropdownMenuContent
        side={side}
        align={align}
        aria-label={t("switchMenu.label")}
        className="max-h-[440px] w-[340px] max-w-[calc(100vw-24px)] overflow-y-auto p-2"
      >
        <DropdownMenuLabel className="px-2 pt-1 pb-2 text-xs leading-relaxed font-normal text-muted-foreground">
          {t("switchMenu.intro")}
        </DropdownMenuLabel>
        {others.map((m) => (
          <DropdownMenuItem key={m.key} className="min-h-10 gap-2.5" onSelect={() => onPick(m.key)}>
            <StatusBadge tone={m.where === "local" ? "neutral" : "info"} icon={null}>
              {te(`where.${m.where}`)}
            </StatusBadge>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate">{m.display}</span>
              <CostBadge where={m.where} price={m.price} />
            </span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="text-xs text-muted-foreground">
          <Link to={paths.models()}>{t("switchMenu.footer")}</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
