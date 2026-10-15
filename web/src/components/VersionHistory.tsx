import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useAdopt, useSetCurrent } from "@/api/hooks/products";
import type { ModelOption } from "@/api/schemas/models";
import type { Product } from "@/api/schemas/products";
import { CostBadge } from "@/components/CostBadge";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { currentVersion, modelName, originLabel, versionStatus } from "@/lib/versions";

/**
 * 「历史」 (SPEC 7.4): every version, newest first. 设为当前 changes what the page shows;
 * 采纳这一版 changes what the next step uses (one adopted version per product).
 */
export function VersionHistory({
  product,
  models,
  componentName,
  className,
}: {
  product: Product;
  models: readonly ModelOption[];
  /** 「小说补全」 */
  componentName: string;
  className?: string;
}) {
  const { t } = useTranslation("components");
  const { t: te } = useTranslation("enums");
  const { t: tc } = useTranslation();
  const setCurrent = useSetCurrent();
  const adopt = useAdopt();
  const cur = currentVersion(product);
  const locked = product.locked_hash !== null;
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));

  if (product.versions.length === 0)
    return <EmptyState className={className} title={t("versions.empty")} />;

  return (
    <div className={cn("flex flex-col gap-2.5", className)}>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {t("versions.intro", { name: componentName })}
      </p>
      <ol
        className="flex flex-col gap-2.5"
        aria-label={t("runBar.history", { count: product.versions.length })}
      >
        {[...product.versions].reverse().map((v) => {
          const isCur = v.id === cur?.id;
          const status = versionStatus(product, v);
          const adopted = status !== "draft";
          return (
            <li
              key={v.id}
              aria-current={isCur ? "true" : undefined}
              className={cn(
                "flex flex-col gap-1.5 rounded-md border bg-card px-3 py-2.5",
                isCur && "border-primary bg-tone-info-bg/60",
              )}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-medium">v{v.n}</span>
                <span className="min-w-0 truncate text-sm">{modelName(models, v.model_key)}</span>
                <StatusBadge tone={adopted ? "info" : "neutral"} icon={null} className="ml-auto">
                  {te(`versionStatus.${status}`)}
                  {isCur ? ` · ${t("versions.current")}` : ""}
                </StatusBadge>
              </div>
              <div className="flex flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
                {v.where ? <span>{te(`where.${v.where}`)} ·</span> : null}
                <span>{formatTime(v.created_at)} ·</span>
                <CostBadge where={v.where ?? "api"} usd={v.cost_usd} />
                <span>· {te(`origin.${originLabel(product, v)}`)}</span>
                {v.note ? <span>· {v.note}</span> : null}
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isCur || setCurrent.isPending}
                  onClick={() => setCurrent.mutate(v.id, { onError })}
                >
                  {t("versions.setCurrent")}
                </Button>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span tabIndex={locked ? 0 : -1}>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={adopted || locked || adopt.isPending}
                        onClick={() =>
                          adopt.mutate(v.id, {
                            onSuccess: () => toast.success(t("versions.adopted", { n: v.n })),
                            onError,
                          })
                        }
                      >
                        {t("versions.adopt")}
                      </Button>
                    </span>
                  </TooltipTrigger>
                  {locked ? <TooltipContent>{t("versions.lockedHint")}</TooltipContent> : null}
                </Tooltip>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
