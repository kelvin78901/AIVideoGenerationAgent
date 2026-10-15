import { TriangleAlert } from "lucide-react";
import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";

const LegacyApp = lazy(() => import("@/legacy/App"));

/** Upstream Hermes UI, kept reachable at /legacy until M2 replaces it (not in the nav). */
export default function LegacyPage() {
  const { t } = useTranslation();
  return (
    <div className="flex h-screen flex-col">
      <div
        role="note"
        title={t("legacy.detail")}
        className="flex shrink-0 items-center gap-2 bg-status-warn px-4 py-1.5 text-sm font-semibold text-white"
      >
        <TriangleAlert className="size-4" aria-hidden />
        <span>{t("legacy.banner")}</span>
        <span className="font-normal opacity-90">{t("legacy.detail")}</span>
      </div>
      <div className="legacy-root min-h-0 flex-1 overflow-auto">
        <Suspense fallback={null}>
          <LegacyApp />
        </Suspense>
      </div>
    </div>
  );
}
