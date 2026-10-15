import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useGate } from "@/api/hooks/gates";
import { useEpisodeProgress } from "@/api/hooks/series";
import { GATE_STEP, type Gate } from "@/api/schemas/gates";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";

/**
 * The page header's 「确认原文，生成剧本 →」 (SPEC 16.2): confirms the step's gate and moves on.
 * Once confirmed it shows 已确认, still leads to the next step, and can be reopened.
 */
export function GateButton({
  gate,
  episodeId,
  label,
  to,
}: {
  gate: Gate;
  episodeId: string | undefined;
  /** Page wording, e.g. 「确认原文，生成剧本」. */
  label: string;
  /** The next step's path. */
  to: string;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const navigate = useNavigate();
  const progress = useEpisodeProgress(episodeId);
  const decide = useGate(gate, episodeId ?? "");
  const confirmed = progress.data?.steps[GATE_STEP[gate]]?.state === "confirmed";
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));

  return (
    <div className="flex items-center gap-2">
      {confirmed ? (
        <>
          <StatusBadge tone="info">{t("gate.confirmed")}</StatusBadge>
          <Button
            variant="ghost"
            size="sm"
            disabled={decide.isPending}
            onClick={() =>
              decide.mutate("reopen", {
                onSuccess: () => toast.info(t("gate.reopened")),
                onError,
              })
            }
          >
            {t("gate.reopen")}
          </Button>
        </>
      ) : null}
      <Button
        size="lg"
        disabled={!episodeId || !progress.data || decide.isPending}
        onClick={() => {
          if (confirmed) void navigate(to);
          else decide.mutate("confirm", { onSuccess: () => void navigate(to), onError });
        }}
      >
        {label}
        <ArrowRight aria-hidden />
      </Button>
    </div>
  );
}
