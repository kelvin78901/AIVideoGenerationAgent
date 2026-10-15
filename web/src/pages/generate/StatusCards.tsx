import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { Job } from "@/api/schemas/jobs";
import type { MachineProfile } from "@/api/schemas/setup";
import type { Product } from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";
import { gpuStatus } from "@/api/hooks/useJobs";
import { formatUsd } from "@/lib/format";

/** One card: caption, the headline and a detail line (prototype 本地 / API / 质检). */
function Card({
  caption,
  value,
  detail,
}: {
  caption: string;
  value: string;
  detail: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border bg-card px-3.5 py-3">
      <div className="text-xs text-muted-foreground">{caption}</div>
      <div className="text-[15px] font-bold">{value}</div>
      <div className="text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}

/**
 * 本地队列 / API 队列 / 自动质检. Queue counts come from the real `/jobs`; the take being made
 * and the QA tallies come from the shots' video products.
 */
export function StatusCards({
  jobs,
  profile,
  shots,
  products,
  spentUsd,
  shotCapUsd,
  modelName,
  dashboardPath,
}: {
  jobs: Job[] | undefined;
  profile: MachineProfile | undefined;
  shots: Shot[];
  products: Product[];
  spentUsd: number | undefined;
  shotCapUsd: number | undefined;
  modelName: (key: string | null | undefined) => string;
  dashboardPath: string;
}) {
  const { t } = useTranslation("generate");
  const gpu = gpuStatus(jobs);
  const apiBusy = (jobs ?? []).filter((j) => j.queue.startsWith("api:") && j.state === "running");
  const gpuName = profile?.machine.gpu;

  const running = shots
    .map((s) => ({ s, p: products.find((p) => p.id === s.video_product_id) }))
    .find(({ p }) => p?.status === "running");

  const versions = products.flatMap((p) => p.versions);
  const pass = versions.filter((v) => v.qa_pass === true).length;
  const fail = versions.filter((v) => v.qa_pass === false).length;
  const reruns = versions.filter((v) => v.origin === "auto_qa_rerun").length;
  const fallbacks = versions.filter((v) => v.origin === "fallback").length;

  return (
    <section aria-label={t("cards.label")} className="grid gap-3 sm:grid-cols-3">
      <Card
        caption={
          gpuName
            ? t("cards.local", { gpu: `${gpuName.name} ${gpuName.vram_gb}GB` })
            : t("cards.localNoGpu")
        }
        value={gpu.running || gpu.queued ? t("cards.busy", { ...gpu }) : t("cards.idle")}
        detail={
          running
            ? t("cards.runningTake", {
                id: running.s.label,
                n: (running.p?.versions.length ?? 0) + 1,
                model: modelName(running.p?.running?.model_key),
              })
            : t("cards.nothingRunning")
        }
      />
      <Card
        caption={t("cards.api")}
        value={t("cards.apiLine", {
          status: apiBusy.length ? t("cards.apiBusy", { count: apiBusy.length }) : t("cards.idle"),
          spent: spentUsd === undefined ? "—" : formatUsd(spentUsd, { cents: true }),
        })}
        detail={
          shotCapUsd === undefined ? null : t("cards.shotCap", { cap: formatUsd(shotCapUsd) })
        }
      />
      <Card
        caption={t("cards.qa")}
        value={t("cards.qaLine", { pass, fail })}
        detail={
          <>
            {t("cards.qaMeta", { rerun: reruns, fallback: fallbacks })} ·{" "}
            <Link to={dashboardPath} className="text-primary underline-offset-4 hover:underline">
              {t("cards.dashboard")}
            </Link>
          </>
        }
      />
    </section>
  );
}
