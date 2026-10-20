import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useApplyImpact, useImpactPreview } from "@/api/hooks/impact";
import { ImpactDialog } from "@/components/ImpactDialog";
import {
  ImpactGuardContext,
  type Guard,
  type GuardedChange,
} from "@/components/impactGuardContext";

/**
 * Where confirmed work can be edited (the novel page, the beat board): while `active`, an
 * edit inside asks `/impact/preview` first and shows the impact dialog (确认并同步 / 只改这里 /
 * 撤销); nothing is written until the user picks. A preview with nothing on it is written at
 * once (只改这里).
 */
export function ImpactGuard({ active, children }: { active: boolean; children: ReactNode }) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const preview = useImpactPreview();
  const apply = useApplyImpact();
  const [pending, setPending] = useState<GuardedChange | null>(null);
  const close = () => {
    setPending(null);
    preview.reset();
  };
  const fail = (err: unknown) => {
    close();
    toast.error(errorMessage(tc, err));
  };

  const guard: Guard = (g) => {
    setPending(g);
    preview.mutate(g.change, {
      onSuccess: (impact) => {
        if (impact.lines.length) return;
        apply.mutate(
          { impact_id: impact.id, action: "mark" },
          {
            onSuccess: () => {
              close();
              toast.success(t("impact.saved"));
              g.onDone?.();
            },
            onError: fail,
          },
        );
      },
      onError: fail,
    });
  };

  const impact = preview.data;
  return (
    <ImpactGuardContext.Provider value={active ? guard : null}>
      {children}
      {pending && impact?.lines.length ? (
        <ImpactDialog
          variant="modal"
          impact={impact}
          title={pending.title}
          detail={pending.detail}
          onOpenChange={(open) => {
            if (!open) close();
          }}
          onResolved={(action) => {
            if (action !== "undo") pending.onDone?.();
          }}
        />
      ) : null}
    </ImpactGuardContext.Provider>
  );
}
