import { lazy, Suspense } from "react";

const LegacyApp = lazy(() => import("@/legacy/App"));

/** Upstream Hermes UI, kept reachable at /legacy until M2 replaces it (not in the nav). */
export default function LegacyPage() {
  return (
    <div className="legacy-root h-screen">
      <Suspense fallback={null}>
        <LegacyApp />
      </Suspense>
    </div>
  );
}
