import { useTranslation } from "react-i18next";

import type { SafeArea } from "@/api/schemas/spec";

/**
 * 安全区: where the platform's UI covers a picture, as dashed boxes laid over it (the spec
 * page's preview names them; on a keyframe or the animatic they stay small and unnamed).
 */
export function SafeAreaOverlay({ area, named = false }: { area: SafeArea; named?: boolean }) {
  const { t } = useTranslation("spec");
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      {area.zones.map((z) => (
        <div
          key={z.key}
          data-testid={`zone-${z.key}`}
          className="absolute border border-dashed border-white/60 bg-white/10 p-1 text-[10px] text-white/85"
          style={{ left: `${z.l}%`, top: `${z.t}%`, width: `${z.w}%`, height: `${z.h}%` }}
        >
          {named ? t(`preview.zone.${z.key}`) : null}
        </div>
      ))}
    </div>
  );
}
