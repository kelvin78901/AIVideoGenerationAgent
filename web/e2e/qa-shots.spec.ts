/**
 * The QA screenshots for docs/studio/reports/ui/ (`pnpm shots`, project `shots-qa`): 生成 on
 * the backend with the demo's QA scenario on (`DRAMA_DEMO_QA=1`), once the QA it starts with
 * and the reruns and repairs that starts have settled. 1-04: T1–T3 passing, T4 only off at the
 * mouths, T5 its automatic 口型修复. Light and dark at 1440 px, light at 2000 px.
 *   pnpm shots -g generate-qa
 */
import { fileURLToPath } from "node:url";

import { test, type Page } from "@playwright/test";

import { openPage, setUi, settleJobs, type Theme } from "./fixtures";

const outDir = fileURLToPath(new URL("../../docs/studio/reports/ui", import.meta.url));
const PATH = "/s/demo/e/1/generate?shot=demo-shot-1-04";

test.beforeAll(async ({ request }) => {
  await settleJobs(request);
});

async function shoot(page: Page, theme: Theme, name: string): Promise<void> {
  await setUi(page, { theme });
  await openPage(page, PATH);
  await page.getByRole("listitem", { name: "候选 T5", exact: true }).waitFor();
  await page.mouse.move(0, 0);
  await page.screenshot({
    path: `${outDir}/${name}.jpg`,
    fullPage: true,
    type: "jpeg",
    quality: 80,
    animations: "disabled",
  });
}

for (const theme of ["light", "dark"] as Theme[]) {
  test(`generate-qa ${theme}`, async ({ page }) => {
    await shoot(page, theme, `generate-qa.${theme}`);
  });
}

test("generate-qa wide", async ({ page }) => {
  await page.setViewportSize({ width: 2000, height: 1100 });
  await shoot(page, "light", "generate-qa-wide.light");
});
