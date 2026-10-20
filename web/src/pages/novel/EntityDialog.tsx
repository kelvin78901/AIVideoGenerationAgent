/**
 * 编辑设定: name, aliases, summary and 冻结 (a rerun of 设定提取 keeps a frozen entry as it is).
 * Each alias can be split off into an entry of its own. Saving makes an adopted `edit` version
 * (`PATCH /bible/{id}`); only the fields that changed are sent.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useEditBibleEntity, useMergeBible } from "@/api/hooks/novel";
import type { BibleEntity, BiblePatch } from "@/api/schemas/novel";
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
import { Input, Label } from "@/components/ui/form";

const splitNames = (text: string) =>
  text
    .split(/[、,，;；]/)
    .map((s) => s.trim())
    .filter(Boolean);

export function EntityDialog({
  seriesId,
  entity,
  onOpenChange,
}: {
  seriesId: string;
  /** The entry being edited; null = closed. */
  entity: BibleEntity | null;
  onOpenChange: (open: boolean) => void;
}) {
  // A fresh form (and mutation state) for every entry.
  return entity ? (
    <EntityForm key={entity.id} seriesId={seriesId} entity={entity} onOpenChange={onOpenChange} />
  ) : null;
}

function EntityForm({
  seriesId,
  entity,
  onOpenChange,
}: {
  seriesId: string;
  entity: BibleEntity;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation("novel");
  const { t: tc } = useTranslation();
  const edit = useEditBibleEntity(seriesId);
  const merge = useMergeBible(seriesId);
  const guard = useImpactGuard();
  const [name, setName] = useState(entity.name);
  const [aliases, setAliases] = useState(entity.aliases.join("、"));
  const [summary, setSummary] = useState(entity.data.summary ?? "");
  const [frozen, setFrozen] = useState(entity.frozen);

  const close = () => onOpenChange(false);

  const save = () => {
    const body: BiblePatch = {};
    if (name.trim() !== entity.name) body.name = name.trim();
    const list = splitNames(aliases);
    if (list.join("、") !== entity.aliases.join("、")) body.aliases = list;
    if (summary.trim() !== (entity.data.summary ?? ""))
      body.data = { ...entity.data, summary: summary.trim() };
    if (frozen !== entity.frozen) body.frozen = frozen;
    if (Object.keys(body).length === 0) return close();
    if (guard)
      return guard({
        change: { kind: "bible_edit", target_id: entity.id, patch: { ...body } },
        title: t("impact.bible"),
        detail: entity.name,
        onDone: close,
      });
    edit.mutate(
      { id: entity.id, ...body },
      {
        onSuccess: (saved) => {
          toast.success(t("bible.dialog.saved", { name: saved.name }));
          close();
        },
      },
    );
  };

  const split = (alias: string) =>
    guard
      ? guard({
          change: {
            kind: "bible_merge",
            target_id: entity.id,
            patch: { action: "split", ids: [entity.id], alias },
          },
          title: t("impact.bible"),
          detail: entity.name,
          onDone: close,
        })
      : merge.mutate(
          { action: "split", ids: [entity.id], alias },
          {
            onSuccess: () => {
              toast.success(t("bible.dialog.splitDone", { alias }));
              close();
            },
            onError: (err) => toast.error(errorMessage(tc, err)),
          },
        );

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg gap-3.5" closeLabel={t("bible.dialog.cancel")}>
        <DialogTitle>{t("bible.dialog.title")}</DialogTitle>
        <DialogDescription>{t("bible.dialog.lead")}</DialogDescription>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bible-name">{t("bible.dialog.name")}</Label>
          <Input id="bible-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bible-aliases">{t("bible.dialog.aliases")}</Label>
          <Input
            id="bible-aliases"
            value={aliases}
            placeholder={t("bible.dialog.aliasesHint")}
            onChange={(e) => setAliases(e.target.value)}
          />
          {entity.aliases.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5">
              {entity.aliases.map((a) => (
                <li key={a}>
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={t("bible.dialog.splitLabel", { alias: a })}
                    disabled={merge.isPending}
                    onClick={() => split(a)}
                  >
                    {a} · {t("bible.dialog.split")}
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bible-summary">{t("bible.dialog.summary")}</Label>
          <Input id="bible-summary" value={summary} onChange={(e) => setSummary(e.target.value)} />
        </div>
        <div className="flex items-start gap-2">
          <Checkbox
            id="bible-frozen"
            checked={frozen}
            onCheckedChange={(v) => setFrozen(v === true)}
            className="mt-0.5"
          />
          <Label htmlFor="bible-frozen" className="leading-snug font-normal">
            {t("bible.dialog.frozen")}
          </Label>
        </div>

        {edit.error ? (
          <p role="alert" className="text-sm text-status-fail">
            {errorMessage(tc, edit.error)}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={close}>
            {t("bible.dialog.cancel")}
          </Button>
          <Button onClick={save} disabled={edit.isPending}>
            {t("bible.dialog.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
