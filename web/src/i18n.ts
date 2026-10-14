import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import enCommon from "@/locales/en/common.json";
import enNav from "@/locales/en/nav.json";
import zhCommon from "@/locales/zh-CN/common.json";
import zhNav from "@/locales/zh-CN/nav.json";
import { useUiStore, type Lang } from "@/stores/ui";

export const resources = {
  "zh-CN": { common: zhCommon, nav: zhNav },
  en: { common: enCommon, nav: enNav },
} as const;

export const defaultNS = "common";

void i18n.use(initReactI18next).init({
  resources,
  lng: useUiStore.getState().lang,
  fallbackLng: "zh-CN",
  defaultNS,
  ns: ["common", "nav"],
  interpolation: { escapeValue: false },
  returnNull: false,
});

function applyLang(lang: Lang): void {
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
}

applyLang(useUiStore.getState().lang);
useUiStore.subscribe((state, prev) => {
  if (state.lang !== prev.lang) applyLang(state.lang);
});

export default i18n;
