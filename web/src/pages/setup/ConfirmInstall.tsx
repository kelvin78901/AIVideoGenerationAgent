/**
 * Approval before an install starts (SPEC 12.2-5, 6.4.1): every change to the user's own ComfyUI
 * (what, from which version to which, where from, how big), then elevation and big downloads.
 * Closing the dialog declines: nothing is installed.
 */
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Message } from "@/api/schemas/common";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";

const str = (v: string | number | undefined) => (v === undefined ? undefined : String(v));

/** No pinned target (`to`) means whatever the source has now: its latest version. */
function useVersionText() {
  const { t } = useTranslation("setup");
  return (m: Message) => {
    const from = str(m.params.from);
    const to = str(m.params.to);
    if (from && to) return t("change.version.fromTo", { from, to });
    if (from) return t("change.version.fromLatest", { from });
    return to ?? t("change.version.latest");
  };
}

export function ConfirmInstall({
  reasons,
  comfyRoot,
  itemName,
  pending,
  onConfirm,
  onCancel,
}: {
  /** `install.confirm`. */
  reasons: Message[];
  /** Where the user's ComfyUI is, when the scan found it. */
  comfyRoot: string | null;
  itemName: (id: string) => string;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation("setup");
  const versionText = useVersionText();
  const changes = reasons.filter((m) => m.code === "comfy_change");
  const others = reasons.filter((m) => m.code !== "comfy_change");
  const name = (m: Message) => itemName(String(m.params.item));

  return (
    <Dialog open onOpenChange={(open) => (!open && !pending ? onCancel() : undefined)}>
      <DialogContent role="alertdialog" className="max-w-2xl gap-3.5">
        <DialogTitle className="flex items-center gap-2 text-base font-bold">
          <AlertTriangle className="size-4 text-tone-warn-fg" aria-hidden />
          {t("confirm.title")}
        </DialogTitle>
        <DialogDescription>{t("confirm.lead")}</DialogDescription>

        {changes.length ? (
          <section aria-labelledby="confirm-comfy" className="flex flex-col gap-2">
            <h3 id="confirm-comfy" className="text-sm font-bold">
              {t("confirm.comfyTitle", { count: changes.length })}
            </h3>
            {comfyRoot ? (
              <div className="font-mono text-xs text-muted-foreground">{comfyRoot}</div>
            ) : null}
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full min-w-[520px] text-[13px]">
                <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-1.5 font-medium">{t("change.col.item")}</th>
                    <th className="px-3 py-1.5 font-medium">{t("change.col.action")}</th>
                    <th className="px-3 py-1.5 font-medium">{t("change.col.version")}</th>
                    <th className="px-3 py-1.5 font-medium">{t("change.col.source")}</th>
                    <th className="px-3 py-1.5 text-right font-medium">{t("change.col.size")}</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((m) => (
                    <tr key={String(m.params.item)} className="border-t border-border/60">
                      <td className="px-3 py-1.5 font-medium">{name(m)}</td>
                      <td className="px-3 py-1.5">
                        {t(`change.action.${m.params.action === "update" ? "update" : "install"}`)}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-xs">{versionText(m)}</td>
                      <td className="max-w-56 truncate px-3 py-1.5 font-mono text-xs text-muted-foreground">
                        <span title={str(m.params.source)}>
                          {str(m.params.source) ?? t("none")}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">
                        {m.params.gb !== undefined
                          ? t("change.size", { gb: m.params.gb })
                          : t("none")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t("confirm.snapshotNote")}
            </p>
          </section>
        ) : null}

        {others.length ? (
          <section
            aria-labelledby={changes.length ? "confirm-other" : undefined}
            className="flex flex-col gap-1.5"
          >
            {changes.length ? (
              <h3 id="confirm-other" className="text-sm font-bold">
                {t("confirm.otherTitle")}
              </h3>
            ) : null}
            <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
              {others.map((m, i) => (
                <li key={i}>
                  {t(`confirmReason.${m.code}` as "confirmReason.admin", {
                    ...m.params,
                    item: name(m),
                    defaultValue: m.code,
                  })}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={onCancel}>
            {t("confirm.cancel")}
          </Button>
          <Button disabled={pending} onClick={onConfirm}>
            {t("confirm.ok")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
