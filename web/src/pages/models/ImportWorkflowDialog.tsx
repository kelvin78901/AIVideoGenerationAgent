/**
 * 导入工作流 (SPEC 6.4.4): drop an API-format JSON exported from ComfyUI, or pick one from
 * ComfyUI's own workflow list. The studio's asset board is listed but cannot be registered.
 */
import { FileJson } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComfyWorkflowFiles, useImportWorkflow } from "@/api/hooks/workflows";
import type { ImportRequest, Workflow } from "@/api/schemas/workflows";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** API format: an object of nodes, each with `class_type` and `inputs`. */
function isApiWorkflow(data: unknown): data is Record<string, unknown> {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  const nodes = Object.values(data);
  return (
    nodes.length > 0 &&
    nodes.every((n) => !!n && typeof n === "object" && "class_type" in n && "inputs" in n)
  );
}

export function ImportWorkflowDialog({
  open,
  onOpenChange,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: (w: Workflow) => void;
}) {
  const { t } = useTranslation("workflows");
  const { t: tc } = useTranslation();
  const files = useComfyWorkflowFiles({ enabled: open });
  const importIt = useImportWorkflow();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const run = (body: ImportRequest) =>
    importIt.mutate(body, {
      onSuccess: (w) => {
        toast.success(t("importDialog.done", { name: w.name }));
        onOpenChange(false);
        onImported(w);
      },
      onError: (err) => toast.error(errorMessage(tc, err)),
    });

  const readFile = async (file: File | undefined) => {
    if (!file) return;
    let data: unknown;
    try {
      data = JSON.parse(await file.text());
    } catch {
      data = null;
    }
    if (!isApiWorkflow(data)) {
      toast.error(t("importDialog.badFile"));
      return;
    }
    run({ file_name: file.name, workflow: data });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl gap-3.5" closeLabel={t("importDialog.close")}>
        <DialogTitle className="text-base font-bold">{t("importDialog.title")}</DialogTitle>
        <DialogDescription>{t("importDialog.lead")}</DialogDescription>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            void readFile(e.dataTransfer.files[0]);
          }}
          className={cn(
            "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center",
            over ? "border-primary bg-accent" : "border-border",
          )}
        >
          <FileJson className="size-6 text-muted-foreground" aria-hidden />
          <div className="text-sm font-medium">{t("importDialog.drop")}</div>
          <div className="text-xs text-muted-foreground">{t("importDialog.dropHint")}</div>
          <Button
            size="sm"
            variant="outline"
            disabled={importIt.isPending}
            onClick={() => input.current?.click()}
          >
            {t("importDialog.pick")}
          </Button>
          <input
            ref={input}
            type="file"
            accept=".json,application/json"
            className="hidden"
            data-testid="workflow-file"
            onChange={(e) => {
              void readFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>

        <section aria-labelledby="comfy-list" className="flex flex-col gap-1.5">
          <h3 id="comfy-list" className="text-sm font-bold">
            {t("importDialog.fromComfy")}
          </h3>
          {files.isPending ? (
            <p className="text-[13px] text-muted-foreground">{t("importDialog.loading")}</p>
          ) : (
            <ul className="max-h-60 overflow-y-auto rounded-lg border">
              {(files.data ?? []).map((f) => {
                const taken = f.board || !!f.imported_as;
                return (
                  <li
                    key={f.path}
                    aria-label={f.path}
                    className="flex items-center gap-3 border-t border-border/60 px-3 py-2 first:border-t-0"
                  >
                    <span
                      className={cn(
                        "min-w-0 flex-1 truncate font-mono text-xs",
                        taken && "text-muted-foreground",
                      )}
                    >
                      {f.path}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatDateTime(f.modified_at)}
                    </span>
                    {taken ? (
                      <span className="w-40 shrink-0 text-right text-xs text-muted-foreground">
                        {t(f.board ? "importDialog.board" : "importDialog.imported")}
                      </span>
                    ) : (
                      <span className="w-40 shrink-0 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={importIt.isPending}
                          onClick={() => run({ comfy_path: f.path })}
                        >
                          {t("importDialog.importThis")}
                        </Button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("importDialog.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
