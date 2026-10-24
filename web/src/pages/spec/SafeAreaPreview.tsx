import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { Aspect, SafeArea } from "@/api/schemas/spec";
import { SafeAreaOverlay } from "@/components/SafeAreaOverlay";
import { ASPECT_RATIO } from "@/lib/safeArea";

/** 构图和安全区: the frame at the chosen aspect with the overlays and the subtitle position. */
export function SafeAreaPreview({
  aspect,
  area,
  showSafe,
  showSub,
  name,
  caption,
  children,
}: {
  aspect: Aspect;
  /** The platform's (`lib/safeArea.ts`). */
  area: SafeArea;
  showSafe: boolean;
  showSub: boolean;
  /** 「9:16 竖版」 */
  name: string;
  /** 「9:16 竖版 · 1080×1920 · 24 fps」 */
  caption: string;
  /** Toggles and the save button under the frame. */
  children?: ReactNode;
}) {
  const { t } = useTranslation("spec");
  const [rw, rh] = ASPECT_RATIO[aspect];
  const vertical = rh > rw;
  const pw = vertical ? Math.round((380 * rw) / rh) : 260;
  const ph = vertical ? 380 : Math.round((260 * rh) / rw);
  const label =
    t("preview.aria", {
      name,
      zones: area.zones.map((z) => t(`preview.zone.${z.key}`)).join(t("preview.zoneSep")),
    }) + (showSub ? t("preview.ariaSub") : "");

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        role="img"
        aria-label={label}
        data-testid="safe-area"
        className="relative overflow-hidden rounded-md bg-media"
        style={{ width: pw, height: ph }}
      >
        {/* A person in the middle, so the overlays read against something. */}
        <div
          aria-hidden
          className="absolute left-1/2 -translate-x-1/2 rounded-t-full bg-media-muted/70"
          style={{ width: "32%", height: "45%", top: "30%" }}
        />
        {showSafe ? <SafeAreaOverlay area={area} named /> : null}
        {showSub ? (
          <div
            data-testid="sub-position"
            className="absolute left-0 text-center text-sm font-bold text-white drop-shadow"
            style={{ top: `${area.subtitle.top}%`, right: `${area.subtitle.right}%` }}
          >
            {t("preview.subSample")}
          </div>
        ) : null}
      </div>
      <div className="font-mono text-xs text-muted-foreground">{caption}</div>
      {children}
    </div>
  );
}
