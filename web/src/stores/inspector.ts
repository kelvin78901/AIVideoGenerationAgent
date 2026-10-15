import { create } from "zustand";

export type InspectorTab = "run" | "prompt" | "history";

interface InspectorState {
  /** Selected component chip; null = the page's first component. */
  component: string | null;
  tab: InspectorTab;
  select: (component: string) => void;
  setTab: (tab: InspectorTab) => void;
  /** RunBar's 「改提示词」 / 「历史」, the post page's clip clicks … */
  show: (tab: InspectorTab, component?: string) => void;
  reset: () => void;
}

/** One Inspector per page (SPEC 16.2); pages reset it when they mount. */
export const useInspectorStore = create<InspectorState>()((set) => ({
  component: null,
  tab: "run",
  select: (component) => set({ component }),
  setTab: (tab) => set({ tab }),
  show: (tab, component) => set((s) => ({ tab, component: component ?? s.component })),
  reset: () => set({ component: null, tab: "run" }),
}));
