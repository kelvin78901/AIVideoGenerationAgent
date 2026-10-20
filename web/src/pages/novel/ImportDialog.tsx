/**
 * 导入 .txt / .docx (SPEC 4.1, 15): pick a file, see what the backend found (`dry_run`: encoding,
 * chapters), confirm the adaptation rights, import. A second import replaces the text in use;
 * the dialog says what that does (DECISIONS 2026-10-19 · M2 plan, 重新导入 = 替换).
 */
import { FileText } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useImportNovel } from "@/api/hooks/novel";
import type { NovelImport, NovelSource } from "@/api/schemas/novel";
import { useImpactGuard } from "@/components/impactGuardContext";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/form";
import { cn } from "@/lib/utils";
import { chapterLabel } from "@/pages/novel/text";

/** Chapters listed in the preview; the rest are counted. */
const PREVIEW_CHAPTERS = 8;
const ACCEPT =
  ".txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function ImportDialog({
  seriesId,
  current,
  open,
  onOpenChange,
  onImported,
}: {
  seriesId: string;
  /** The text in use, if any: importing replaces it. */
  current: NovelSource | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: () => void;
}) {
  const { t } = useTranslation("novel");
  const { t: tc } = useTranslation();
  const scan = useImportNovel(seriesId);
  const save = useImportNovel(seriesId);
  // Replacing a confirmed novel previews its impact first, with the file the scan stored.
  const guard = useImpactGuard();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [rights, setRights] = useState(false);
  const [over, setOver] = useState(false);
  const preview = scan.data;

  const close = (next: boolean) => {
    if (!next) {
      setFile(null);
      setRights(false);
      scan.reset();
      save.reset();
    }
    onOpenChange(next);
  };

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    scan.mutate({ file: f, dryRun: true });
  };

  const submit = () => {
    if (!file || !preview) return;
    if (guard && preview.upload_id)
      return guard({
        change: {
          kind: "novel_replace",
          target_id: seriesId,
          patch: { upload_id: preview.upload_id, filename: file.name },
        },
        title: t("impact.replace"),
        detail: file.name,
        onDone: () => {
          close(false);
          onImported();
        },
      });
    save.mutate(
      { file, dryRun: false, rightsConfirmed: true },
      {
        onSuccess: (result) => {
          if (result.unchanged) toast.info(t("importDialog.unchanged"));
          else
            toast.success(
              t("importDialog.done", {
                filename: result.filename,
                chapters: result.chapters.length,
                chars: result.chars,
              }),
            );
          close(false);
          onImported();
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-xl gap-3.5" closeLabel={t("importDialog.cancel")}>
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
            pick(e.dataTransfer.files[0]);
          }}
          className={cn(
            "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-5 text-center",
            over ? "border-primary bg-accent" : "border-border",
          )}
        >
          <FileText className="size-6 text-muted-foreground" aria-hidden />
          <div className="text-sm font-medium">{file ? file.name : t("importDialog.drop")}</div>
          <Button
            size="sm"
            variant="outline"
            disabled={scan.isPending || save.isPending}
            onClick={() => input.current?.click()}
          >
            {t("importDialog.pick")}
          </Button>
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            className="hidden"
            data-testid="novel-file"
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>

        {scan.isPending ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t("importDialog.reading")}
          </p>
        ) : null}
        {scan.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(tc, scan.error)}
          </p>
        ) : null}
        {preview ? <Preview preview={preview} /> : null}

        {preview && current ? (
          <p className="rounded-md bg-tone-warn-bg px-3 py-2 text-[13px] leading-relaxed text-tone-warn-fg">
            {t("importDialog.replace", { filename: current.filename })}
          </p>
        ) : null}

        <div className="flex items-start gap-2">
          <Checkbox
            id="novel-rights"
            checked={rights}
            onCheckedChange={(v) => setRights(v === true)}
            className="mt-0.5"
          />
          <Label htmlFor="novel-rights" className="leading-snug font-normal">
            {t("importDialog.rights")}
          </Label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            {t("importDialog.cancel")}
          </Button>
          <Button onClick={submit} disabled={!preview || !rights || save.isPending}>
            {t("importDialog.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Preview({ preview }: { preview: NovelImport }) {
  const { t } = useTranslation("novel");
  const shown = preview.chapters.slice(0, PREVIEW_CHAPTERS);
  const rest = preview.chapters.length - shown.length;
  return (
    <section aria-labelledby="novel-preview" className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 id="novel-preview" className="text-sm font-bold">
          {t(preview.split_by === "heading" ? "importDialog.found" : "importDialog.foundParts", {
            chapters: preview.chapters.length,
            chars: preview.chars,
          })}
        </h3>
        <span className="text-xs text-muted-foreground">
          {t(`importDialog.encoding.${preview.encoding}`)}
        </span>
      </div>
      <ol className="flex flex-col gap-0.5 text-[13px]">
        {shown.map((c) => (
          <li key={c.idx} className="flex gap-2">
            <span className="min-w-0 flex-1 truncate">{chapterLabel(t, c, preview.split_by)}</span>
            <span className="shrink-0 text-muted-foreground tabular-nums">
              {t("chapter.chars", { chars: c.chars })}
            </span>
          </li>
        ))}
      </ol>
      {rest > 0 ? (
        <p className="text-xs text-muted-foreground">{t("importDialog.more", { count: rest })}</p>
      ) : null}
    </section>
  );
}
