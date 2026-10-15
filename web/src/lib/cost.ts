/** Money and time wording shared by CostBadge, pickers and the dashboard. */
import type { TFunction } from "i18next";

import type { Price } from "@/api/schemas/common";
import { formatMoney } from "@/lib/format";

/** "约 40 秒" / "约 2 分钟". */
export function formatDuration(t: TFunction<"components">, seconds: number): string {
  return seconds < 90
    ? t("cost.seconds", { n: Math.max(1, Math.round(seconds)) })
    : t("cost.minutes", { n: Math.round(seconds / 60) });
}

/** "$1.32 / $3.96 每百万 token", "$0.04 / 张" … */
export function formatPrice(t: TFunction<"components">, price: Price): string {
  if (price.unit === "mtok")
    return t("cost.perMtok", {
      in: formatMoney(price.in, price.currency),
      out: formatMoney(price.out, price.currency),
    });
  const amount = formatMoney(price.amount, price.currency);
  if (price.unit === "image") return t("cost.perImage", { amount });
  if (price.unit === "second") return t("cost.perSecond", { amount });
  return t("cost.perCall", { amount });
}
