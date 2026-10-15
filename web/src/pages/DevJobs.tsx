import { CheckCircle2, CircleDashed, Clock, Loader2, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { apiSpend, useJobs, useLlmTest, useModelCalls } from "@/api/hooks/useJobs";
import type { Job, JobState, ModelCall } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const STATE_VARIANT: Record<JobState, "pass" | "fail" | "warn" | "secondary" | "outline"> = {
  queued: "secondary",
  waiting_confirm: "warn",
  running: "outline",
  succeeded: "pass",
  failed: "fail",
  canceled: "secondary",
};

function StateIcon({ state }: { state: JobState }) {
  if (state === "running") return <Loader2 className="animate-spin" aria-hidden />;
  if (state === "succeeded") return <CheckCircle2 aria-hidden />;
  if (state === "failed") return <XCircle aria-hidden />;
  if (state === "waiting_confirm") return <Clock aria-hidden />;
  return <CircleDashed aria-hidden />;
}

function time(value: string | null): string {
  return value ? new Date(value).toLocaleTimeString() : "—";
}

function usd(value: number): string {
  return value < 0.01 && value > 0 ? `$${value.toFixed(5)}` : `$${value.toFixed(2)}`;
}

function JobRow({ job }: { job: Job }) {
  const { t } = useTranslation("dev");
  const model = typeof job.result?.model_key === "string" ? job.result.model_key : null;
  return (
    <tr className="border-t" data-testid={`job-${job.id}`}>
      <td className="px-2 py-1.5 font-mono text-xs">{job.id.slice(0, 8)}</td>
      <td className="px-2 py-1.5 font-mono text-xs">{job.kind}</td>
      <td className="px-2 py-1.5 font-mono text-xs">{job.queue}</td>
      <td className="px-2 py-1.5">
        <Badge variant={STATE_VARIANT[job.state]}>
          <StateIcon state={job.state} />
          {t(`state.${job.state}`)}
        </Badge>
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {job.attempt}/{job.max_attempts}
      </td>
      <td className="px-2 py-1.5 tabular-nums">{time(job.created_at)}</td>
      <td className="px-2 py-1.5 font-mono text-xs">{job.error?.code ?? model ?? "—"}</td>
    </tr>
  );
}

function CallRow({ call }: { call: ModelCall }) {
  const { t } = useTranslation("dev");
  return (
    <tr className="border-t">
      <td className="px-2 py-1.5 tabular-nums">{time(call.started_at)}</td>
      <td className="px-2 py-1.5 font-mono text-xs">{call.model_key}</td>
      <td className="px-2 py-1.5">{t(`where.${call.where}`)}</td>
      <td className="px-2 py-1.5">
        <Badge variant={call.status === "success" ? "pass" : "fail"}>
          {call.status === "success" ? <CheckCircle2 aria-hidden /> : <XCircle aria-hidden />}
          {t(`status.${call.status}`)}
        </Badge>
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {call.tokens_in ?? "—"} / {call.tokens_out ?? "—"}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">{usd(call.cost_usd)}</td>
    </tr>
  );
}

function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-md border bg-card">
      <table className="w-full text-sm">
        <thead className="bg-muted text-left text-xs text-muted-foreground">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-2 py-1.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/** Developer panel for the M0 acceptance check (only routed in dev builds). */
export default function DevJobsPage() {
  const { t } = useTranslation("dev");
  const { t: tc } = useTranslation();
  const { t: tn } = useTranslation("nav");
  const jobs = useJobs();
  const calls = useModelCalls();
  const llmTest = useLlmTest();

  const start = () =>
    llmTest.mutate(
      { delay_s: 3 },
      {
        onSuccess: (job) => toast.success(t("queued", { id: job.id.slice(0, 8) })),
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );

  return (
    <section className="flex flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{tn("pages.devJobs")}</h1>
        <Button onClick={start} disabled={llmTest.isPending} className="ml-auto">
          {llmTest.isPending ? t("llmTestPending") : t("llmTest")}
        </Button>
      </header>
      <p className="text-muted-foreground">{t("intro")}</p>

      <h2 className="font-semibold">{t("jobs")}</h2>
      <Table
        head={[
          t("col.id"),
          t("col.kind"),
          t("col.queue"),
          t("col.state"),
          t("col.attempt"),
          t("col.created"),
          t("col.result"),
        ]}
      >
        {jobs.data?.length ? (
          jobs.data.map((job) => <JobRow key={job.id} job={job} />)
        ) : (
          <tr>
            <td colSpan={7} className="px-2 py-3 text-center text-muted-foreground">
              {jobs.isError ? errorMessage(tc, jobs.error) : t("empty")}
            </td>
          </tr>
        )}
      </Table>

      <h2 className="font-semibold">{t("calls")}</h2>
      <p className="text-muted-foreground" data-testid="calls-total">
        {t("total", { count: calls.data?.length ?? 0, cost: usd(apiSpend(calls.data)) })}
      </p>
      <Table
        head={[
          t("col.time"),
          t("col.model"),
          t("col.where"),
          t("col.status"),
          t("col.tokens"),
          t("col.cost"),
        ]}
      >
        {calls.data?.length ? (
          calls.data.map((call) => <CallRow key={call.id} call={call} />)
        ) : (
          <tr>
            <td colSpan={6} className="px-2 py-3 text-center text-muted-foreground">
              {t("empty")}
            </td>
          </tr>
        )}
      </Table>
    </section>
  );
}
