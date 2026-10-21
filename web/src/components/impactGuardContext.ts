import { createContext, useContext, type ReactNode } from "react";

import type { ImpactChange } from "@/api/schemas/impact";

/** An edit of confirmed work, or of work something confirmed was built from. */
export interface GuardedChange {
  change: ImpactChange;
  /** The dialog's title: what the edit reaches (「改原文会影响已确认的内容」). */
  title: string;
  detail?: ReactNode;
  /** Once written: 只改这里, 确认并同步, or nothing downstream after all. 撤销 leaves the edit
   * where it was on the page. */
  onDone?: () => void;
}

export type Guard = (g: GuardedChange) => void;

export const ImpactGuardContext = createContext<Guard | null>(null);

/**
 * Inside `<ImpactGuard active>` edits preview their impact first (SPEC 16.2, M2 step 10);
 * null: write them directly, as before anything was confirmed.
 */
export const useImpactGuard = () => useContext(ImpactGuardContext);
