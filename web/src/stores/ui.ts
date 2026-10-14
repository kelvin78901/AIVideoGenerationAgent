import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Lang = "zh-CN" | "en";
export type Theme = "light" | "dark";

interface UiState {
  lang: Lang;
  theme: Theme;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  setTheme: (theme: Theme) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      lang: "zh-CN",
      theme: "light",
      setLang: (lang) => set({ lang }),
      toggleLang: () => set({ lang: get().lang === "zh-CN" ? "en" : "zh-CN" }),
      setTheme: (theme) => set({ theme }),
    }),
    { name: "drama-studio.ui" },
  ),
);
