import { useMutation, useQueryClient } from "@tanstack/react-query";

import { post } from "@/api/client";
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
      void client.invalidateQueries({ queryKey: ["episodes"] });
      void client.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}
