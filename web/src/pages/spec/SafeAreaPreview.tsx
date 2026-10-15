import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { Aspect, Platform } from "@/api/schemas/spec";

const RATIO: Record<Aspect, [number, number]> = {
  "9:16": [9, 16],
  "16:9": [16, 9],
  "3:4": [3, 4],
  "1:1": [1, 1],
  "21:9": [21, 9],
};

interface Zone {
  key: "top" | "buttons" | "caption" | "controls" | "controlsWide";
  l: number;
  t: number;
  w: number;
  h: number;
}

/**
 * Where platform UI covers the picture (prototype Spec.dc.html, approximate): portrait
 * short-drama apps have a top bar, a button column and the caption block; other players only
 * their controls. Percentages of the frame.
 */
function zonesFor(
  aspect: Aspect,
  platform: Platform,
): { zones: Zone[]; subTop: number; subRight: number } {
  const [w, h] = RATIO[aspect];
  const vertical = h > w;
  const app = platform === "cn" || platform === "intl" || (platform === "custom" && vertical);
  if (vertical && app)
    return {
      zones: [
        { key: "top", l: 0, t: 0, w: 100, h: 7 },
        { key: "buttons", l: 84, t: 38, w: 16, h: 42 },
        { key: "caption", l: 0, t: 82, w: 100, h: 18 },
      ],
      subTop: 70,
      subRight: 16,
    };
  return {
    zones: [{ key: vertical ? "controls" : "controlsWide", l: 0, t: 86, w: 100, h: 14 }],
    subTop: vertical ? 76 : 72,
    subRight: 0,
  };
}

/** 构图和安全区: the frame at the chosen aspect with the overlays and the subtitle position. */
export function SafeAreaPreview({
  aspect,
  platform,
  showSafe,
  showSub,
  name,
  caption,
  children,
}: {
  aspect: Aspect;
  platform: Platform;
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
  const [rw, rh] = RATIO[aspect];
  const vertical = rh > rw;
  const pw = vertical ? Math.round((380 * rw) / rh) : 260;
  const ph = vertical ? 380 : Math.round((260 * rh) / rw);
  const { zones, subTop, subRight } = zonesFor(aspect, platform);
  const label =
    t("preview.aria", {
      name,
      zones: zones.map((z) => t(`preview.zone.${z.key}`)).join(t("preview.zoneSep")),
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
        {showSafe
          ? zones.map((z) => (
              <div
                key={z.key}
                data-testid={`zone-${z.key}`}
                className="absolute border border-dashed border-white/60 bg-white/10 p-1 text-[10px] text-white/85"
                style={{ left: `${z.l}%`, top: `${z.t}%`, width: `${z.w}%`, height: `${z.h}%` }}
              >
                {t(`preview.zone.${z.key}`)}
              </div>
            ))
          : null}
        {showSub ? (
          <div
            data-testid="sub-position"
            className="absolute left-0 text-center text-sm font-bold text-white drop-shadow"
            style={{ top: `${subTop}%`, right: `${subRight}%` }}
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
