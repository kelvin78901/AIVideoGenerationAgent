import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import enAssets from "@/locales/en/assets.json";
import enCommon from "@/locales/en/common.json";
import enComponents from "@/locales/en/components.json";
import enDev from "@/locales/en/dev.json";
import enEnums from "@/locales/en/enums.json";
import enNav from "@/locales/en/nav.json";
import enNovel from "@/locales/en/novel.json";
import enScript from "@/locales/en/script.json";
import zhAssets from "@/locales/zh-CN/assets.json";
import zhCommon from "@/locales/zh-CN/common.json";
import zhComponents from "@/locales/zh-CN/components.json";
import zhDev from "@/locales/zh-CN/dev.json";
import zhEnums from "@/locales/zh-CN/enums.json";
import zhNav from "@/locales/zh-CN/nav.json";
import zhNovel from "@/locales/zh-CN/novel.json";
import zhScript from "@/locales/zh-CN/script.json";
import { useUiStore, type Lang } from "@/stores/ui";

export const resources = {
  "zh-CN": {
    common: zhCommon,
    components: zhComponents,
    enums: zhEnums,
    nav: zhNav,
    novel: zhNovel,
    script: zhScript,
    assets: zhAssets,
    dev: zhDev,
  },
  en: {
    common: enCommon,
    components: enComponents,
    enums: enEnums,
    nav: enNav,
    novel: enNovel,
    script: enScript,
    assets: enAssets,
    dev: enDev,
  },
} as const;

export const defaultNS = "common";

void i18n.use(initReactI18next).init({
  resources,
  lng: useUiStore.getState().lang,
  fallbackLng: "zh-CN",
  defaultNS,
  ns: ["common", "components", "enums", "nav", "novel", "script", "assets", "dev"],
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
