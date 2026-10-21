/**
 * 新建剧集… (DECISIONS 2026-10-19 · M2 plan): a title, then the output spec page (SPEC 16.1
 * 「新建剧集时必经」), then the novel page to import.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useCreateSeries } from "@/api/hooks/series";
import { SeriesCreateSchema } from "@/api/schemas/series";
import { paths } from "@/app/paths";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/form";
import { useUiStore } from "@/stores/ui";

export function NewSeriesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const create = useCreateSeries();
  const navigate = useNavigate();
  const lang = useUiStore((s) => s.lang);
  const [title, setTitle] = useState("");
  const [invalid, setInvalid] = useState(false);

  const close = (next: boolean) => {
    if (!next) {
      setTitle("");
      setInvalid(false);
      create.reset();
    }
    onOpenChange(next);
  };

  const submit = () => {
    const body = SeriesCreateSchema.safeParse({ title, ui_lang: lang });
    if (!body.success) {
      setInvalid(true);
      return;
    }
    create.mutate(body.data, {
      onSuccess: (s) => {
        toast.success(t("newSeries.done", { title: s.title }));
        useUiStore.getState().setLastSeries(s.id);
        close(false);
        void navigate(paths.spec(s.id));
      },
      onError: (err) => toast.error(errorMessage(t, err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-md gap-3.5" closeLabel={t("newSeries.cancel")}>
        <DialogTitle className="text-base font-bold">{t("newSeries.title")}</DialogTitle>
        <DialogDescription>{t("newSeries.lead")}</DialogDescription>
        <form
          className="flex flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Label htmlFor="new-series-title">{t("newSeries.name")}</Label>
          <Input
            id="new-series-title"
            value={title}
            maxLength={80}
            autoFocus
            placeholder={t("newSeries.placeholder")}
            aria-invalid={invalid || undefined}
            aria-describedby={invalid ? "new-series-error" : undefined}
            className="h-9"
            onChange={(e) => {
              setTitle(e.target.value);
              setInvalid(false);
            }}
          />
          {invalid ? (
            <p id="new-series-error" className="text-xs text-destructive">
              {t("newSeries.required")}
            </p>
          ) : null}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            {t("newSeries.cancel")}
          </Button>
          <Button onClick={submit} disabled={create.isPending}>
            {t("newSeries.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
