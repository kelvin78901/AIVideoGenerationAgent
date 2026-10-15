import { expect, type Page } from "@playwright/test";

export type Theme = "light" | "dark";
export type Lang = "zh-CN" | "en";

/** Seeds the persisted UI store (stores/ui.ts) before the app boots. */
export async function setUi(page: Page, ui: { lang?: Lang; theme?: Theme }): Promise<void> {
  const state = { lang: ui.lang ?? "zh-CN", theme: ui.theme ?? "light" };
  await page.addInitScript((value) => {
    localStorage.setItem("drama-studio.ui", JSON.stringify({ state: value, version: 0 }));
  }, state);
}

/** Opens a route and waits until its data has loaded (no `[data-loading]` left). */
export async function openPage(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await expect(page.locator("main#main")).toBeVisible();
  await expect(page.locator("[data-loading]")).toHaveCount(0, { timeout: 15_000 });
  // Let late layout (fonts) settle before assertions and screenshots.
  await page.evaluate(() => document.fonts.ready);
}

/** Collects console errors; the API client logs every contract violation (`bad_response`). */
export function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  // Name the failing request: the console message alone does not say which URL failed.
  page.on("response", (resp) => {
    if (resp.status() >= 500) errors.push(`HTTP ${resp.status()} ${resp.url()}`);
  });
  return errors;
}
