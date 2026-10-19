import { ArrowLeftRight, ChevronDown, Clock, Loader2, Pencil, RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { ModelOption } from "@/api/schemas/models";
import type { Product } from "@/api/schemas/products";
import { CostBadge } from "@/components/CostBadge";
import { ModelSwitchMenu } from "@/components/ModelSwitchMenu";
import { useRunAction } from "@/components/useRunAction";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { currentVersion, modelName, versionStatus } from "@/lib/versions";

/**
 * The four buttons over every product (SPEC 7.4, 16.2): 改提示词 / 重跑 (生成页「再出一条」)
 * / 不满意换一个 ▾ / 历史 n, with the current version and the rerun estimate.
 */
export function RunBar({
  product,
  what,
  models,
  onEditPrompt,
  onOpenHistory,
  variant = "default",
  className,
}: {
  product: Product;
  /** What the product is, from the page: 「补全建议 · 4 条」. */
  what: string;
  /** The component's models in fallback order (names, prices, the switch menu). */
  models: readonly ModelOption[];
  onEditPrompt: () => void;
  onOpenHistory: () => void;
  /** `take`: video candidates, where rerunning adds one more take (「再出一条」). */
  variant?: "default" | "take";
  className?: string;
}) {
  const { t } = useTranslation("components");
  const { t: te } = useTranslation("enums");
  const action = useRunAction(product.id);
  const cur = currentVersion(product);
  const busy = action.pending || product.running !== null;
  const busyModel = product.running?.model_key ?? action.pendingModel ?? cur?.model_key;
  const est = product.estimate;

  return (
    <div
      data-slot="run-bar"
      className={cn(
        "relative flex flex-wrap items-center gap-x-2.5 gap-y-2 rounded-lg border bg-card px-3 py-2.5",
        className,
      )}
    >
      <div className="flex min-w-48 flex-1 flex-col gap-0.5">
        <div className="text-xs text-muted-foreground">{t("runBar.product", { what })}</div>
        {cur ? (
          <div className="text-sm font-medium">
            {/* A hand edit or an import has no model: say what made it instead. */}v{cur.n} ·{" "}
            {cur.model_key ? modelName(models, cur.model_key) : te(`origin.${cur.origin}`)}{" "}
            <span className="font-normal text-muted-foreground">
              {cur.where ? `· ${te(`where.${cur.where}`)} ` : ""}· {formatTime(cur.created_at)} ·{" "}
              {te(`versionStatus.${versionStatus(product, cur)}`)}
            </span>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">{t("runBar.noVersion")}</div>
        )}
      </div>
      {busy ? (
        <div role="status" className="flex items-center gap-1.5 text-sm text-primary">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          {t(
            product.running?.state === "waiting_confirm"
              ? "runBar.waiting"
              : product.status === "queued"
                ? "runBar.queued"
                : "runBar.running",
            { model: modelName(models, busyModel) },
          )}
        </div>
      ) : null}
      <Button variant="outline" onClick={onEditPrompt}>
        <Pencil aria-hidden />
        {t("runBar.editPrompt")}
      </Button>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* The span keeps the tooltip working while the button is disabled. */}
          <span tabIndex={busy ? 0 : -1}>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => action.run({ mode: product.versions.length ? "rerun" : "run" })}
            >
              <RotateCw aria-hidden />
              {t(variant === "take" ? "runBar.more" : "runBar.rerun")}
              {est ? <CostBadge where={est.where} usd={est.cost_usd} estimate compact /> : null}
            </Button>
          </span>
        </TooltipTrigger>
        {est ? (
          <TooltipContent>
            <CostBadge
              where={est.where}
              usd={est.cost_usd}
              estimate
              seconds={est.seconds}
              className="text-inherit"
            />{" "}
            · {modelName(models, est.model_key)}
          </TooltipContent>
        ) : null}
      </Tooltip>
      <ModelSwitchMenu
        options={models}
        currentKey={cur?.model_key}
        onPick={(model) => action.run({ mode: "switch", model })}
      >
        <Button variant="outline" disabled={busy}>
          <ArrowLeftRight aria-hidden />
          {t("runBar.switch")}
          <ChevronDown className="size-3.5" aria-hidden />
        </Button>
      </ModelSwitchMenu>
      <Button variant="outline" onClick={onOpenHistory}>
        <Clock aria-hidden />
        {t("runBar.history", { count: product.versions.length })}
      </Button>
    </div>
  );
}
