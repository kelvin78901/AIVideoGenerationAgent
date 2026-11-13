import { ImagePlus, X } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { usePictureSet, type PictureFile } from "@/api/hooks/pictures";
import { Button } from "@/components/ui/button";

const SELECT =
  "h-8 rounded-md border bg-card px-1.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

/**
 * A set of the user's own pictures, each with what it is for (镜头参考图, 风格板; 16c: 多参考图):
 * small square thumbnails, 删掉 on each, and 上传 with the purpose picked first. Adding and
 * removing are new versions, adopted at once (`pipeline/pictures.py`).
 */
export function PictureSet({
  label,
  pictures,
  purposes,
  purposeLabel,
  max,
  path,
  owner,
  disabled,
  addLabel,
}: {
  /** 「镜头参考图」: the group's name, and the upload button's context. */
  label: string;
  pictures: PictureFile[];
  /** What a picture can be for; one: no choice to make. */
  purposes: readonly string[];
  purposeLabel: (purpose: string) => string;
  max: number;
  /** `/shots/{id}/refs`, `/series/{id}/style-board` */
  path: string;
  /** The product list it is in (`shot:<id>`, `series:<id>`). */
  owner: string;
  disabled?: boolean;
  /** The upload button (default 「上传参考图」). */
  addLabel?: string;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const { add, remove } = usePictureSet({ path, owner });
  const input = useRef<HTMLInputElement>(null);
  const [purpose, setPurpose] = useState(purposes[0] ?? "");
  const full = pictures.length >= max;
  const busy = add.isPending || remove.isPending;
  const fail = (err: unknown) => toast.error(errorMessage(tc, err));

  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-end gap-3">
      {pictures.map((p) => {
        const what = purposeLabel(p.purpose ?? purposes[0] ?? "");
        const name = t("pictures.set.picture", { label, n: p.idx + 1, purpose: what });
        return (
          <figure key={`${p.idx}-${p.sha256}`} className="flex w-24 flex-col gap-1">
            <div className="relative aspect-square overflow-hidden rounded-md bg-media">
              <img src={fileUrl(p.sha256)} alt={name} className="size-full object-cover" />
              {disabled ? null : (
                <button
                  type="button"
                  aria-label={t("pictures.set.remove", { name })}
                  title={t("pictures.set.remove", { name })}
                  disabled={busy}
                  onClick={() => remove.mutate(p.idx, { onError: fail })}
                  className="absolute top-1 right-1 flex size-6 items-center justify-center rounded-md bg-black/50 text-white outline-none hover:bg-black/70 focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="size-3.5" aria-hidden />
                </button>
              )}
            </div>
            {purposes.length > 1 ? (
              <figcaption className="text-xs text-muted-foreground">{what}</figcaption>
            ) : null}
          </figure>
        );
      })}
      {disabled ? null : (
        <div className="flex flex-col gap-1.5">
          {purposes.length > 1 ? (
            <select
              className={SELECT}
              aria-label={t("pictures.set.purpose")}
              value={purpose}
              disabled={full || busy}
              onChange={(e) => setPurpose(e.target.value)}
            >
              {purposes.map((p) => (
                <option key={p} value={p}>
                  {purposeLabel(p)}
                </option>
              ))}
            </select>
          ) : null}
          <Button
            size="sm"
            variant="outline"
            disabled={full || busy}
            onClick={() => input.current?.click()}
          >
            <ImagePlus aria-hidden />
            {addLabel ?? t("pictures.set.add")}
          </Button>
          <span className="text-xs text-muted-foreground">
            {full
              ? t("pictures.set.full", { max })
              : t("pictures.set.count", { count: pictures.length, max })}
          </span>
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            aria-label={t("pictures.set.file", { label })}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file)
                add.mutate(
                  { file, purpose: purposes.length > 1 ? purpose : undefined },
                  { onError: fail },
                );
            }}
          />
        </div>
      )}
    </div>
  );
}
