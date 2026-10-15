import { expect, test } from "@playwright/test";

import { openPage, setUi, trackConsoleErrors } from "./fixtures";
import { PAGES } from "./pages";

for (const p of PAGES) {
  test(`${p.id} opens without errors and switches language`, async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await setUi(page, { lang: "zh-CN" });
    await openPage(page, p.path);
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toBeVisible();
    const zh = (await h1.textContent()) ?? "";
    await page.getByRole("button", { name: "切换界面语言 / Switch language" }).click();
    await expect(h1).not.toHaveText(zh);
    expect(errors).toEqual([]);
  });
}

test("demo badge is shown while the page uses demo data", async ({ page }) => {
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/novel");
  await expect(page.getByTestId("demo-badge")).toHaveText("示例数据");
});

test("real jobs still update live over SSE behind the demo worker", async ({ page }) => {
  await setUi(page, {});
  await openPage(page, "/dev/jobs");
  await page.getByRole("button", { name: "发起一次 Mock LLM 调用" }).click();
  await expect(page.getByRole("cell", { name: "完成", exact: true })).toBeVisible({
    timeout: 20_000,
  });
});

test("a locked spec changes aspect through the impact dialog and keeps it after reload", async ({
  page,
}) => {
  const errors = trackConsoleErrors(page);
  await setUi(page, {});
  const tag = (text: string) => page.getByRole("link", { name: text });
  const change = async (platform: RegExp, aspect: string) => {
    await page.getByRole("button", { name: platform }).click();
    await page.getByRole("button", { name: "改，并标记待更新" }).click();
    await expect(page.getByText(/会影响已经做好的部分/)).toHaveCount(0);
    // Written to the real backend (MSW's /impact/apply calls PUT …/spec?confirmed_impact=).
    await page.reload();
    await expect(page.locator("[data-loading]")).toHaveCount(0, { timeout: 15_000 });
    await expect(tag(aspect)).toBeVisible();
  };
  await openPage(page, "/s/demo/spec");
  await expect(tag("9:16 · 1080×1920 · 24 fps")).toBeVisible();
  await change(/横屏平台/, "16:9 · 1920×1080 · 24 fps");
  // Back to 9:16 so later tests see the demo spec.
  await change(/国内短剧平台/, "9:16 · 1080×1920 · 24 fps");
  expect(errors).toEqual([]);
});
