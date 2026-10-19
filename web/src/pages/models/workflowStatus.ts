/** How a workflow's tier, bindings and health check read in the library (SPEC 6.4.4). */
import { useTranslation } from "react-i18next";

import type { Workflow, WorkflowTier } from "@/api/schemas/workflows";
import type { Tone } from "@/lib/tone";

export const tierTone: Record<WorkflowTier, Tone> = {
  recommended: "info",
  mine: "pass",
  unverified: "neutral",
};

export const pendingCount = (w: Workflow) => w.bindings.filter((b) => b.state === "guessed").length;

/** What the 体检 column says: bindings to confirm come first, they block everything else. */
export function useCheckText() {
  const { t } = useTranslation("workflows");
  return (w: Workflow): { text: string; tone: Tone } => {
    const pending = pendingCount(w);
    if (pending) return { text: t("status.pending", { count: pending }), tone: "warn" };
    const c = w.check;
    if (!c) return { text: t("status.never"), tone: "neutral" };
    const packs = c.missing_packs.length;
    const models = c.missing_models.length;
    if (packs && models) return { text: t("status.missing", { packs, models }), tone: "warn" };
    if (packs) return { text: t("status.missingPacks", { count: packs }), tone: "warn" };
    if (models) return { text: t("status.missingModels", { count: models }), tone: "warn" };
    if (c.problems.length)
      return { text: t("status.broken", { count: c.problems.length }), tone: "fail" };
    return { text: t("status.ok"), tone: "pass" };
  };
}
