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
