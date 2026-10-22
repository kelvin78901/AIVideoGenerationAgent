import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

export interface LightboxItem {
  src: string;
  label: string;
}

/**
 * A picture at the size the screen allows (candidates and views are small cards): fitted to the
 * viewport, ← → (or the buttons) for the others of the same set.
 */
export function MediaLightbox({
  items,
  index,
  onIndex,
}: {
  items: LightboxItem[];
  /** The one shown; null = closed. */
  index: number | null;
  onIndex: (index: number | null) => void;
}) {
  const { t } = useTranslation("components");
  const item = index !== null ? items[index] : undefined;
  const many = items.length > 1;
  const step = (by: number) => {
    if (index !== null && many) onIndex((index + by + items.length) % items.length);
  };
  return (
    <Dialog open={item !== undefined} onOpenChange={(open) => !open && onIndex(null)}>
      {item ? (
        <DialogContent
          closeLabel={t("lightbox.close")}
          className="max-h-[96vh] w-auto max-w-[min(94vw,1400px)] gap-3 p-4"
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") step(-1);
            else if (e.key === "ArrowRight") step(1);
          }}
        >
          <DialogTitle className="pr-8 text-sm font-medium">{item.label}</DialogTitle>
          <DialogDescription className="sr-only">
            {many ? t("lightbox.hintMany") : t("lightbox.hint")}
          </DialogDescription>
          <img
            src={item.src}
            alt={item.label}
            className="mx-auto max-h-[80vh] max-w-full rounded-md object-contain"
          />
          {many ? (
            <div className="flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" onClick={() => step(-1)}>
                <ChevronLeft aria-hidden />
                {t("lightbox.prev")}
              </Button>
              <span className="text-xs text-muted-foreground tabular-nums">
                {t("lightbox.position", { n: (index ?? 0) + 1, total: items.length })}
              </span>
              <Button variant="outline" size="sm" onClick={() => step(1)}>
                {t("lightbox.next")}
                <ChevronRight aria-hidden />
              </Button>
            </div>
          ) : null}
        </DialogContent>
      ) : null}
    </Dialog>
  );
}
