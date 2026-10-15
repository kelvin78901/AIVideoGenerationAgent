/**
 * Full-page screenshots for docs/studio/reports/ui/ (Chinese, light and dark).
 *   pnpm shots                 all pages
 *   pnpm shots -g novel        one page
 *   SHOTS_LANG=en pnpm shots   English, into node_modules/.playwright/shots-en (not committed)
 */
import { fileURLToPath } from "node:url";

import { test } from "@playwright/test";

import { openPage, setUi, type Lang, type Theme } from "./fixtures";
import { PAGES } from "./pages";

const lang: Lang = process.env.SHOTS_LANG === "en" ? "en" : "zh-CN";
const outDir = fileURLToPath(
  lang === "zh-CN"
    ? new URL("../../docs/studio/reports/ui", import.meta.url)
    : new URL("../node_modules/.playwright/shots-en", import.meta.url),
);

for (const p of PAGES) {
  for (const theme of ["light", "dark"] as Theme[]) {
    test(`${p.id} ${theme}`, async ({ page }) => {
      await setUi(page, { lang, theme });
      await openPage(page, p.path);
      await page.mouse.move(0, 0);
      await page.screenshot({
        path: `${outDir}/${p.id}.${theme}.jpg`,
        fullPage: true,
        type: "jpeg",
        quality: 80,
        animations: "disabled",
      });
    });
  }
}
