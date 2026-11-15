import {
  ChevronDown,
  ImageUp,
  Maximize,
  PaintBucket,
  RefreshCw,
  Upload,
  Wand2,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComponentCatalog } from "@/api/hooks/config";
import { useUpscalePicture } from "@/api/hooks/pictures";
import { InpaintDialog } from "@/components/pictures/InpaintDialog";
import { RedrawDialog, type PictureTarget } from "@/components/pictures/RedrawDialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function Item({
  icon,
  label,
  hint,
  disabled,
  title,
  onSelect,
}: {
  icon: ReactNode;
  label: string;
  hint?: string;
  disabled?: boolean;
  /** Why it is disabled. */
  title?: string;
  onSelect: () => void;
}) {
  return (
    <DropdownMenuItem
      className="min-h-9 gap-2"
      disabled={disabled}
      title={title}
      onSelect={onSelect}
    >
      {icon}
      <span className="flex grow flex-col">
        {label}
        {/* A disabled item takes no hover: the reason is written out. */}
        {disabled && title ? <span className="text-xs text-muted-foreground">{title}</span> : null}
      </span>
      {hint ? <small className="text-xs text-muted-foreground">{hint}</small> : null}
    </DropdownMenuItem>
  );
}

/**
 * 换来源 ▾ (草图 S3): what can happen to the picked picture — draw again, upload one's own (the
 * owner opens its crop dialog), 以这张为底重画, 局部修复, 放大 (only locally: greyed with the
 * reason when this machine cannot). Each makes a new version; history keeps the old one.
 */
export function PictureMenu({
  target,
  upscaleTo,
  regenerate,
  onUpload,
  uploadHint,
  disabled,
  label,
}: {
  /** The picked picture; null when there is none yet (only 重新生成 and 上传). */
  target: PictureTarget | null;
  /** 放大到 this size; null: the picture is that size already. */
  upscaleTo: { w: number; h: number } | null;
  regenerate?: { label: string; hint?: string; busy?: boolean; onSelect: () => void };
  onUpload?: () => void;
  /** 「按 9:16 裁」 */
  uploadHint?: string;
  disabled?: boolean;
  label?: string;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const [redraw, setRedraw] = useState<PictureTarget | null>(null);
  const [inpaint, setInpaint] = useState<PictureTarget | null>(null);
  const upscale = useUpscalePicture();
  const iup = useComponentCatalog().data?.components.find((c) => c.id === "iup");
  const blocked = iup?.unavailable.local;
  const cannot = blocked
    ? t(`picker.unavailable.${blocked.code}` as "picker.unavailable.machine", blocked.params)
    : !iup
      ? undefined
      : iup.local_models.length
        ? undefined
        : t("picker.unavailable.no_local_model");

  const runUpscale = (p: PictureTarget, size: { w: number; h: number }) =>
    upscale.mutate(
      { productId: p.productId, versionId: p.versionId, idx: p.idx },
      {
        onSuccess: () =>
          toast.info(t("pictures.upscale.started", { name: p.name, w: size.w, h: size.h })),
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );

  return (
    <>
      {/* Not modal: a modal menu that opens a dialog leaves `pointer-events: none` on the body. */}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild disabled={disabled}>
          <Button size="sm" variant="outline">
            <ImageUp aria-hidden />
            {label ?? t("pictures.menu")}
            <ChevronDown aria-hidden className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-72 p-1.5">
          {regenerate ? (
            <Item
              icon={<RefreshCw className="size-4" aria-hidden />}
              label={regenerate.label}
              hint={regenerate.hint}
              disabled={regenerate.busy}
              onSelect={regenerate.onSelect}
            />
          ) : null}
          {onUpload ? (
            <Item
              icon={<Upload className="size-4" aria-hidden />}
              label={t("pictures.upload")}
              hint={uploadHint}
              onSelect={onUpload}
            />
          ) : null}
          {target ? (
            <>
              {regenerate || onUpload ? <DropdownMenuSeparator /> : null}
              <Item
                icon={<Wand2 className="size-4" aria-hidden />}
                label={t("pictures.redraw.item")}
                hint={target.name}
                onSelect={() => setRedraw(target)}
              />
              <Item
                icon={<PaintBucket className="size-4" aria-hidden />}
                label={t("pictures.inpaint.item")}
                hint={target.name}
                onSelect={() => setInpaint(target)}
              />
              <Item
                icon={<Maximize className="size-4" aria-hidden />}
                label={
                  upscaleTo
                    ? t("pictures.upscale.item", { w: upscaleTo.w, h: upscaleTo.h })
                    : t("pictures.upscale.itemPlain")
                }
                hint={upscaleTo && !cannot ? t("pictures.upscale.hint") : undefined}
                disabled={!upscaleTo || !!cannot || upscale.isPending}
                title={!upscaleTo ? t("pictures.upscale.already") : cannot}
                onSelect={() => upscaleTo && runUpscale(target, upscaleTo)}
              />
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      <RedrawDialog target={redraw} onClose={() => setRedraw(null)} />
      <InpaintDialog target={inpaint} onClose={() => setInpaint(null)} />
    </>
  );
}
