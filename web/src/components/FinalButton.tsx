import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComponentModels, useResolvedConfig } from "@/api/hooks/config";
import { useRunProduct } from "@/api/hooks/products";
import type { Product, ProductVersion } from "@/api/schemas/products";
import { Button } from "@/components/ui/button";
import { formatUsd } from "@/lib/format";

/**
 * 「用 API 出终版」 (hybrid mode, SPEC 7.7): the picked local draft becomes the reference of one
 * picture on the route's API model, a new version whose parent is the draft. Shown for a local
 * draft while the product (an asset, a keyframe) is not locked; the price is that model's, for
 * one picture.
 */
export function FinalButton({
  componentId,
  product,
  version,
  pick,
  letter,
}: {
  componentId: string;
  product: Product;
  version: ProductVersion;
  pick: number;
  letter: string;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const config = useResolvedConfig(componentId).data?.values;
  const models = useComponentModels(componentId);
  const run = useRunProduct(product.id);
  const apiModel = config?.api_model ?? null;
  if (config?.mode !== "hybrid" || !apiModel || version.stage !== "draft" || product.locked_hash)
    return null;
  const model = models.find((m) => m.key === apiModel);
  const price = model?.price;
  const cost = price && price.unit === "image" && price.currency === "USD" ? price.amount : null;
  const busy = run.isPending || product.running !== null;
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={() =>
        run.mutate(
          {
            mode: "run",
            where: "api",
            params: { source_version_id: version.id, source_idx: pick },
          },
          {
            onSuccess: () =>
              toast.info(t("final.started", { letter, model: model?.display ?? apiModel })),
            onError: (err) => toast.error(errorMessage(tc, err)),
          },
        )
      }
    >
      <Sparkles aria-hidden />
      {cost !== null
        ? t("final.buttonCost", { cost: formatUsd(cost, { cents: true }) })
        : t("final.button")}
    </Button>
  );
}
