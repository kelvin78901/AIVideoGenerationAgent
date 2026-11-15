import { useTranslation } from "react-i18next";

import type { Where } from "@/api/schemas/common";
import type { WhereChoice } from "@/components/pictures/useWhereChoices";
import { SegmentedControl } from "@/components/SegmentedControl";
import { formatUsd } from "@/lib/format";

/** 用哪个模型: the route's local model (免费) or its API model (per picture). */
export function WherePicker({
  choices,
  value,
  onChange,
}: {
  choices: WhereChoice[];
  value: Where;
  onChange: (where: Where) => void;
}) {
  const { t } = useTranslation("components");
  if (!choices.length)
    return <p className="text-xs text-muted-foreground">{t("pictures.noModel")}</p>;
  return (
    <SegmentedControl
      size="sm"
      label={t("pictures.model")}
      value={value}
      onChange={onChange}
      options={choices.map((c) => ({
        value: c.where,
        label:
          c.where === "local"
            ? t("pictures.local", { model: c.name })
            : c.cost !== null
              ? t("pictures.apiCost", { model: c.name, cost: formatUsd(c.cost, { cents: true }) })
              : c.name,
      }))}
    />
  );
}
