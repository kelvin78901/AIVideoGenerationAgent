/**
 * Full-page screenshots for docs/studio/reports/ui/ (Chinese, light and dark).
 *   pnpm shots                 all pages
 *   pnpm shots -g novel        one page
 *   SHOTS_LANG=en pnpm shots   English, into node_modules/.playwright/shots-en (not committed)
 */
import { fileURLToPath } from "node:url";

import { test, type Page } from "@playwright/test";

import { openPage, setUi, type Lang, type Theme } from "./fixtures";
import { PAGES } from "./pages";

const lang: Lang = process.env.SHOTS_LANG === "en" ? "en" : "zh-CN";
const outDir = fileURLToPath(
  lang === "zh-CN"
    ? new URL("../../docs/studio/reports/ui", import.meta.url)
    : new URL("../node_modules/.playwright/shots-en", import.meta.url),
);

/** Some sections load after the page's own data (the workflow library, late rows): wait until
 * the page stops growing, or the full-page shot is cut off at whatever height it had then. */
async function settle(page: Page): Promise<void> {
  let last = -1;
  for (let i = 0; i < 40; i++) {
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    if (height === last) return;
    last = height;
    await page.waitForTimeout(300);
  }
}

for (const p of PAGES) {
  for (const theme of ["light", "dark"] as Theme[]) {
    test(`${p.id} ${theme}`, async ({ page }) => {
      await setUi(page, { lang, theme });
      await openPage(page, p.path);
      await settle(page);
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
