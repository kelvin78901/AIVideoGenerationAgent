import { ArrowRight, Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { CompatRow, CompatStatus } from "@/api/schemas/spec";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const statusStyle: Record<CompatStatus, { icon: typeof Check; className: string }> = {
  native: { icon: Check, className: "text-tone-pass-fg" },
  convert: { icon: ArrowRight, className: "text-tone-warn-fg" },
  unsupported: { icon: X, className: "text-tone-fail-fg" },
};

/** 兼容表 (SPEC 13.3): each stage's model on the route against the chosen aspect. */
export function CompatTable({
  rows,
  aspectName,
  modelName,
}: {
  rows: CompatRow[];
  aspectName: string;
  modelName: (key: string) => string;
}) {
  const { t } = useTranslation("spec");
  return (
    <section
      aria-labelledby="compat-title"
      className="flex flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="compat-title" className="text-base font-bold">
          {t("compat.title")}
        </h2>
        <span className="text-xs text-muted-foreground">{t("compat.note")}</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("compat.stageCol")}</TableHead>
            <TableHead>{t("compat.modelCol")}</TableHead>
            <TableHead>{aspectName}</TableHead>
            <TableHead>{t("compat.howCol")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const { icon: Icon, className } = statusStyle[r.status];
            return (
              <TableRow key={r.stage}>
                <TableCell>{t(`compat.stage.${r.stage}` as "compat.stage.keyframe")}</TableCell>
                <TableCell>{r.model_keys.map(modelName).join(" / ")}</TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 font-medium whitespace-nowrap",
                      className,
                    )}
                  >
                    <Icon className="size-3.5" aria-hidden />
                    {t(`compat.status.${r.status}`)}
                  </span>
                </TableCell>
                <TableCell className="whitespace-normal text-muted-foreground">
                  {t(`compat.how.${r.how.code}` as "compat.how.native_4k", {
                    ...r.how.params,
                    defaultValue: r.how.code,
                  })}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </section>
  );
}
