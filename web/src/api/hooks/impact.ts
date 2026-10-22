import { useMutation, useQueryClient } from "@tanstack/react-query";

import { post } from "@/api/client";
import { dubKeys } from "@/api/hooks/dub";
import { productKeys } from "@/api/hooks/products";
import {
  ApplyImpactResultSchema,
  ImpactSchema,
  type ImpactAction,
  type ImpactChange,
} from "@/api/schemas/impact";

/** What a change would invalidate downstream (SPEC 9.1 `POST /impact/preview`). */
export function useImpactPreview() {
  return useMutation({
    mutationFn: (change: ImpactChange) => post("/impact/preview", ImpactSchema, change),
  });
}

/** 只标记 / 自动重跑 / 撤销: progress badges (「待更新 N」) and products refresh afterwards. */
export function useApplyImpact() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { impact_id: string; action: ImpactAction }) =>
      post("/impact/apply", ApplyImpactResultSchema, body),
    onSuccess: () => {
      // The edit itself is written by apply: the novel, bible, suggestions and plan (under
      // ["series"]), the script and badges (["episodes"]).
      void client.invalidateQueries({ queryKey: ["series"] });
      void client.invalidateQueries({ queryKey: ["episodes"] });
      void client.invalidateQueries({ queryKey: productKeys.all });
      // A reworded line or a new voice leaves dubbing 待更新 (M3).
      void client.invalidateQueries({ queryKey: dubKeys.all });
    },
  });
}
