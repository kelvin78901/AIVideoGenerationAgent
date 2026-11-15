import { ImagePlus } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, post } from "@/api/client";
import { useCreateAsset, usePatchAsset, useUploadAsset } from "@/api/hooks/assets";
import {
  NEW_ASSET_KINDS,
  type Asset,
  type NewAssetKind,
  type Physical,
} from "@/api/schemas/assets";
import { JobSchema } from "@/api/schemas/jobs";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/form";

const FIELDS = ["size", "material", "wear"] as const;
const SOURCES = ["generate", "upload"] as const;
type Source = (typeof SOURCES)[number];

/** 新建素材 (草图 A4): one the analysis did not find. Its kind, name and description (a prop also
 * its size, material and wear), then where its picture comes from: candidates drawn from the
 * description, or an upload. An analysis keeps it as written. */
export function NewAssetDialog({
  seriesId,
  open,
  onClose,
  onCreated,
}: {
  seriesId: string;
  open: boolean;
  onClose: () => void;
  onCreated: (asset: Asset) => void;
}) {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const { t: tc } = useTranslation();
  const ids = useId();
  const create = useCreateAsset(seriesId);
  const patch = usePatchAsset(seriesId);
  const upload = useUploadAsset(seriesId);
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<NewAssetKind>("prop");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [physical, setPhysical] = useState<Physical>({ size: "", material: "", wear: "" });
  const [source, setSource] = useState<Source>("generate");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setName("");
    setDescription("");
    setPhysical({ size: "", material: "", wear: "" });
    setSource("generate");
    setFile(null);
  };
  const close = () => {
    reset();
    onClose();
  };
  const ready = name.trim() !== "" && (source === "generate" || file !== null) && !saving;

  const submit = async () => {
    setSaving(true);
    let made: Asset;
    try {
      made = await create.mutateAsync({ kind, name: name.trim(), description: description.trim() });
    } catch (err) {
      toast.error(errorMessage(tc, err));
      setSaving(false);
      return;
    }
    // The asset is there now: whatever fails next, it is shown and can be finished by hand.
    try {
      const given = Object.fromEntries(
        FIELDS.map((k) => [k, physical[k]?.trim() ?? ""]).filter(([, v]) => v),
      );
      if (kind === "prop" && Object.keys(given).length)
        await patch.mutateAsync({ id: made.id, patch: { physical: given } });
      if (source === "upload" && file) await upload.mutateAsync({ id: made.id, file });
      else
        await post(`/products/${encodeURIComponent(made.product_id)}/run`, JobSchema, {
          mode: "run",
        });
      toast.success(
        t(source === "upload" ? "create.doneUpload" : "create.doneGenerate", { name: made.name }),
      );
    } catch (err) {
      toast.error(errorMessage(tc, err));
    }
    setSaving(false);
    onCreated(made);
    close();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? undefined : close())}>
      <DialogContent className="max-w-xl gap-3.5" closeLabel={t("create.cancel")}>
        <DialogTitle className="text-base font-bold">{t("create.title")}</DialogTitle>
        <DialogDescription className="sr-only">{t("create.foot")}</DialogDescription>
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-medium">{t("create.kind")}</div>
          <SegmentedControl
            label={t("create.kind")}
            value={kind}
            onChange={setKind}
            options={NEW_ASSET_KINDS.map((k) => ({ value: k, label: te(`assetKind.${k}`) }))}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${ids}-name`}>{t("create.name")}</Label>
          <Input
            id={`${ids}-name`}
            maxLength={60}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${ids}-desc`}>{t("create.desc")}</Label>
          <Textarea
            id={`${ids}-desc`}
            rows={3}
            maxLength={2000}
            value={description}
            placeholder={t("create.descPlaceholder")}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        {kind === "prop" ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {FIELDS.map((k) => (
              <div key={k} className="flex flex-col gap-1.5">
                <Label htmlFor={`${ids}-${k}`}>{t(`prop.${k}`)}</Label>
                <Input
                  id={`${ids}-${k}`}
                  maxLength={200}
                  value={physical[k] ?? ""}
                  placeholder={t(`prop.${k}Placeholder`)}
                  onChange={(e) => setPhysical((p) => ({ ...p, [k]: e.target.value }))}
                />
              </div>
            ))}
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-medium">{t("create.source")}</div>
          <SegmentedControl
            label={t("create.source")}
            value={source}
            onChange={setSource}
            options={SOURCES.map((s) => ({ value: s, label: t(`create.sources.${s}`) }))}
          />
          {source === "upload" ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => input.current?.click()}>
                <ImagePlus aria-hidden />
                {t("create.pick")}
              </Button>
              <span className="text-xs text-muted-foreground">
                {file ? file.name : t("create.noFile")}
              </span>
              <input
                ref={input}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                aria-label={t("detail.uploadFile")}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  e.target.value = "";
                }}
              />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{t("create.generateHint")}</p>
          )}
        </div>
        <DialogFooter className="items-center">
          <span className="mr-auto text-xs text-muted-foreground">{t("create.foot")}</span>
          <Button variant="outline" onClick={close}>
            {t("create.cancel")}
          </Button>
          <Button disabled={!ready} onClick={() => void submit()}>
            {t("create.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
