import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useRunProduct } from "@/api/hooks/products";
import type { RunRequest } from "@/api/schemas/products";

/** Runs a product and reports failures as a toast; shared by RunBar and PromptEditor. */
export function useRunAction(productId: string) {
  const { t } = useTranslation();
  const run = useRunProduct(productId);
  return {
    run: (body: RunRequest) =>
      run.mutate(body, { onError: (err) => toast.error(errorMessage(t, err)) }),
    pending: run.isPending,
    pendingModel: run.isPending ? run.variables?.model : undefined,
  };
}
