import { useTranslation } from "react-i18next";

import type { Price, Where } from "@/api/schemas/common";
import { formatDuration, formatPrice } from "@/lib/cost";
import { formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Money next to a run, a version or a model (SPEC 16.2):
 * - `where="local"` → 「无 API 费用」 (`compact`: 「免费」)
 * - `price` → list price; `price={null}` on an API model → 「按量计费」
 * - `usd` → the billed cost, or with `estimate` the pre-run estimate 「预计 ≈$0.02」
 * - `seconds` appends 「约 40 秒」
 */
export function CostBadge({
  where,
  usd,
  price,
  estimate = false,
  seconds,
  compact = false,
  className,
}: {
  where: Where;
  usd?: number;
  price?: Price | null;
  estimate?: boolean;
  seconds?: number | null;
  compact?: boolean;
  className?: string;
}) {
  const { t } = useTranslation("components");
  let text: string;
  if (where === "local") text = t(compact ? "cost.freeShort" : "cost.free");
  else if (price !== undefined) text = price ? formatPrice(t, price) : t("cost.metered");
  else if (usd === undefined) text = t("cost.metered");
  else if (estimate)
    text = t(compact ? "cost.approx" : "cost.estimate", {
      amount: formatUsd(usd, { cents: true }),
    });
  else text = formatUsd(usd, { cents: true });
  if (seconds != null && !compact) text += ` · ${formatDuration(t, seconds)}`;
  return (
    <span
      data-slot="cost-badge"
      className={cn("text-xs whitespace-nowrap text-muted-foreground tabular-nums", className)}
    >
      {text}
    </span>
  );
}
