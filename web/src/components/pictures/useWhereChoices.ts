import { useComponentCatalog, useComponentModels, useResolvedConfig } from "@/api/hooks/config";
import type { Where } from "@/api/schemas/common";

export interface WhereChoice {
  where: Where;
  /** The route's model there (`local_model` / `api_model`). */
  name: string;
  /** Per picture in USD; null for local models (free) or an unpriced one. */
  cost: number | null;
}

/** The route's local and API model of a picture component (重画, 局部修复), the ones this
 * machine and these keys can use; the route's own mode first. */
export function useWhereChoices(componentId: string): { choices: WhereChoice[]; initial: Where } {
  const config = useResolvedConfig(componentId).data?.values;
  const def = useComponentCatalog().data?.components.find((c) => c.id === componentId);
  const models = useComponentModels(componentId);
  const choices = (["local", "api"] as const).flatMap((where): WhereChoice[] => {
    const key = where === "local" ? config?.local_model : config?.api_model;
    if (!key || def?.unavailable[where]) return [];
    const model = models.find((m) => m.key === key);
    const price = model?.price;
    const cost =
      where === "api" && price && price.unit === "image" && price.currency === "USD"
        ? price.amount
        : null;
    return [{ where, name: model?.display ?? key, cost }];
  });
  const preferred: Where = config?.mode === "api" ? "api" : "local";
  return {
    choices,
    initial: choices.some((c) => c.where === preferred)
      ? preferred
      : (choices[0]?.where ?? preferred),
  };
}
