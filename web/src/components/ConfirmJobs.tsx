/**
 * Runs that wait for a yes (SPEC 7.5–7.6, hard rule 6): over the per-call cap, over what is
 * left of the episode budget, or a fallback set to 「兜底前先问我」. Mounted once in the shell; it
 * reads the real job list (kept live by `job.updated`) and asks about one run at a time.
 */
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { useComponentCatalog } from "@/api/hooks/config";
import { errorMessage } from "@/api/client";
import { useCancelJob, useConfirmJob, useJobs } from "@/api/hooks/useJobs";
import { JobConfirmSchema, type Job } from "@/api/schemas/jobs";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatCost } from "@/lib/format";
import { modelName } from "@/lib/versions";

function waitingRun(jobs: Job[] | undefined): Job | undefined {
  return (jobs ?? [])
    .filter((j) => j.kind === "product.run" && j.state === "waiting_confirm")
    .sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
}

export function ConfirmJobs() {
  const jobs = useJobs();
  const job = waitingRun(jobs.data);
  return job ? <ConfirmDialog key={job.id} job={job} /> : null;
}

function ConfirmDialog({ job }: { job: Job }) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const { t: te } = useTranslation("enums");
  const models = useComponentCatalog().data?.models ?? [];
  const confirm = useConfirmJob();
  const cancel = useCancelJob();
  const parsed = JobConfirmSchema.safeParse(job.params.confirm);
  const why = parsed.success ? parsed.data : null;
  const model = modelName(
    models,
    typeof job.params.model_key === "string" ? job.params.model_key : null,
  );
  const unpriced = why?.reason === "unpriced" || why?.priced === false;
  const estimate = unpriced
    ? t("confirmJob.unknownPrice")
    : formatCost(why?.estimate_usd ?? job.est_cost_usd ?? 0);
  const limit = formatCost(why?.limit_usd ?? 0);
  const component = job.component_id
    ? te(`component.${job.component_id}` as "component.extract")
    : "";
  const busy = confirm.isPending || cancel.isPending;
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));

  return (
    <Dialog open onOpenChange={() => undefined}>
      <DialogContent
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{t("confirmJob.title", { component })}</DialogTitle>
          <DialogDescription>
            {why?.reason === "fallback"
              ? t("confirmJob.fallback", {
                  failed: modelName(models, why.failed_model ?? null),
                  error: why.error ?? "",
                  model,
                  estimate,
                })
              : why?.reason === "unpriced"
                ? t("confirmJob.unpriced", { model })
                : why?.reason === "episode"
                  ? t("confirmJob.episode", { model, estimate, limit })
                  : why?.reason === "shot"
                    ? t("confirmJob.shot", { model, estimate, limit })
                    : t("confirmJob.perCall", { model, estimate, limit })}
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {t("confirmJob.where")}{" "}
          <Link to="/models" className="text-primary underline-offset-4 hover:underline">
            {t("confirmJob.models")}
          </Link>
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => cancel.mutate(job.id, { onError })}
          >
            {t("confirmJob.cancel")}
          </Button>
          <Button disabled={busy} onClick={() => confirm.mutate(job.id, { onError })}>
            {t("confirmJob.confirm", { estimate })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
