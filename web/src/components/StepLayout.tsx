import type { ReactNode } from "react";

/**
 * A production step page: the work area, and the Inspector as a full-height column on the right
 * (prototype layout). Narrow windows stack it under the work area.
 */
export function StepLayout({ inspector, children }: { inspector: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col lg:flex-row">
      <div className="flex min-w-0 flex-1 flex-col gap-4 px-7 py-6">{children}</div>
      <div className="flex shrink-0 flex-col border-t lg:w-[360px] lg:border-t-0 xl:w-[400px] [&>aside]:flex-1">
        {inspector}
      </div>
    </div>
  );
}
