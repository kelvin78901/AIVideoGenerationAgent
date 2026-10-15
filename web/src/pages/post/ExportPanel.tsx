import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useExport } from "@/api/hooks/post";
import type { ExportCheck, ExportFormat } from "@/api/schemas/timeline";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const statusColor: Record<ExportCheck["status"], string> = {
  pass: "text-tone-info-fg",
  warn: "text-tone-warn-fg",
  fail: "text-tone-fail-fg",
};

/** 导出: the checks, then MP4 at the output spec, FCPXML for Resolve, OTIO and SRT. */
export function ExportPanel({
  episodeId,
  checks,
  specTag,
}: {
  episodeId: string | undefined;
  checks: ExportCheck[];
  /** 「9:16 · 1080×1920 · 24 fps」 from the output spec. */
  specTag: string;
}) {
  const { t } = useTranslation("post");
  const { t: tc } = useTranslation();
  const exp = useExport(episodeId);
  const placeholders = checks.find((c) => c.message.code === "placeholders");
  const count = Number(placeholders?.message.params.count ?? 0);

  const start = (format: ExportFormat) =>
    exp.mutate(format, {
      onSuccess: () =>
        toast.success(
          format === "mp4" && count
            ? t("export.toast.mp4Placeholders", { count })
            : t(`export.toast.${format}`),
        ),
      onError: (err) => toast.error(errorMessage(tc, err)),
    });

  return (
    <section
      aria-labelledby="export-title"
      className="flex min-w-0 flex-1 basis-80 flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <h2 id="export-title" className="text-base font-bold">
        {t("export.title")}
      </h2>
      <ul className="flex flex-col gap-1.5 text-sm">
        {checks.map((c) => (
          <li key={c.message.code} className="flex gap-3">
            <span className={cn("w-10 shrink-0 font-medium", statusColor[c.status])}>
              {t(`export.status.${c.status}`)}
            </span>
            <span>
              {t(`export.check.${c.message.code}` as "export.check.frames", {
                ...c.message.params,
                defaultValue: c.message.code,
              })}
            </span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button size="lg" onClick={() => start("mp4")}>
          {t("export.mp4", { spec: specTag })}
        </Button>
        <Button size="lg" variant="outline" onClick={() => start("fcpxml")}>
          {t("export.fcpxml")}
        </Button>
        <Button size="lg" variant="outline" onClick={() => start("otio")}>
          {t("export.otio")}
        </Button>
        <Button size="lg" variant="outline" onClick={() => start("srt")}>
          {t("export.srt")}
        </Button>
      </div>
    </section>
  );
}
