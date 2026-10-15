import { create } from "zustand";

/** Response header set by every MSW demo handler (`mocks/http.ts`). */
export const DEMO_HEADER = "x-drama-demo";

interface DemoState {
  /** The route currently on screen; kept in sync by the shell. */
  route: string;
  /** Routes that have shown at least one demo response this session. */
  routes: Record<string, true>;
  setRoute: (route: string) => void;
  /** Called by `api()` when a response carries the demo header. */
  markDemoResponse: () => void;
  reset: () => void;
}

export const useDemoStore = create<DemoState>()((set, get) => ({
  route: "/",
  routes: {},
  setRoute: (route) => set({ route }),
  markDemoResponse: () => {
    const { route, routes } = get();
    if (!routes[route]) set({ routes: { ...routes, [route]: true } });
  },
  reset: () => set({ route: "/", routes: {} }),
}));
