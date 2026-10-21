import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Lang = "zh-CN" | "en";
export type Theme = "light" | "dark";

interface UiState {
  lang: Lang;
  theme: Theme;
  /** The series last opened: `/` and pages outside a series go back to it. */
  lastSeries: string | null;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  setTheme: (theme: Theme) => void;
  setLastSeries: (id: string | null) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      lang: "zh-CN",
      theme: "light",
      lastSeries: null,
      setLang: (lang) => set({ lang }),
      toggleLang: () => set({ lang: get().lang === "zh-CN" ? "en" : "zh-CN" }),
      setTheme: (theme) => set({ theme }),
      setLastSeries: (lastSeries) => set({ lastSeries }),
    }),
    { name: "drama-studio.ui" },
  ),
);
