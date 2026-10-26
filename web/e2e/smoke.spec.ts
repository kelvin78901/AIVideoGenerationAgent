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
  const started = page.waitForResponse((r) => r.url().endsWith("/api/v1/dev/llm-test"));
  await page.getByRole("button", { name: "发起一次 Mock LLM 调用" }).click();
  // Its own row: earlier tests (m2.spec.ts) leave finished jobs in the list.
  const { id } = (await (await started).json()) as { id: string };
  await expect(
    page.getByTestId(`job-${id}`).getByRole("cell", { name: "完成", exact: true }),
  ).toBeVisible({ timeout: 20_000 });
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
    // Written by the backend's /impact/apply (`spec_aspect`, M4); the shots' confirmations go.
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

test("first run: / opens 环境与安装; installing into ComfyUI asks first, snapshots, rolls back", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const errors = trackConsoleErrors(page);
  await setUi(page, {});
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup$/);
  const nav = page.getByRole("navigation", { name: "制作步骤" });
  await expect(nav.getByRole("link", { name: "环境与安装" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await page.getByRole("button", { name: "开始检测" }).click();
  const summary = page.getByRole("region", { name: "检测结果" });
  await expect(summary.getByRole("status")).toHaveText("检测完成", { timeout: 20_000 });
  await expect(nav.getByTestId("setup-badge")).toHaveText("缺 15 项");
  await expect(page.getByRole("region", { name: "你的 ComfyUI" })).toContainText("D:\\ComfyUI");

  await page.getByRole("button", { name: "全选" }).click();
  await page.getByRole("button", { name: "安装选中的 16 项" }).click();
  const dialog = page.getByRole("alertdialog", { name: "开始安装前请确认" });
  await expect(dialog.getByText("会改动你的 ComfyUI（10 项）")).toBeVisible();
  await dialog.getByRole("button", { name: "确认，开始安装" }).click();
  await expect(page.getByRole("heading", { name: "准备好了" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/^已存 ComfyUI 快照：/)).toBeVisible();
  // Still missing: H3 and SeedVR2 nodes (with a newer ComfyUI), our own nodes (not out yet).
  await expect(nav.getByTestId("setup-badge")).toHaveText("缺 3 项");

  const snapshots = page.getByRole("list", { name: "快照" });
  await expect(snapshots.getByRole("listitem")).toHaveCount(1);
  await snapshots.getByRole("button", { name: /^回滚到 .* 的快照$/ }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "回滚", exact: true }).click();
  await expect(
    page.getByText("已排上回滚。重启 ComfyUI 后点「重新检测」，核对有没有回滚成功"),
  ).toBeVisible();
  await expect(snapshots.getByRole("listitem")).toContainText(
    "已排上回滚：重启 ComfyUI 后点「重新检测」核对",
  );
  // The scan after the restart checks it (the sample ComfyUI is as the snapshot has it).
  await page.getByRole("button", { name: "重新检测" }).click();
  await expect(snapshots.getByRole("listitem")).toContainText("核对过）", { timeout: 30_000 });
  expect(errors).toEqual([]);

  // Back to a fresh sample PC, so later tests see the first-run page. Each switch has to land
  // before the next: clicking the machine already shown does nothing.
  const machine = page.getByRole("radiogroup", { name: "示例机器（原型演示用）" });
  for (const name of ["Mac M4 Pro", "Windows + RTX 5090"]) {
    await machine.getByRole("radio", { name }).click();
    await expect(machine.getByRole("radio", { name })).toHaveAttribute("aria-checked", "true");
  }
  await expect(page.getByRole("button", { name: "开始检测" })).toBeVisible();
});

test("环境与安装 is in the left nav on every page", async ({ page }) => {
  await setUi(page, {});
  await openPage(page, "/s/demo/spec");
  await page
    .getByRole("navigation", { name: "制作步骤" })
    .getByRole("link", { name: "环境与安装" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("先看看这台电脑能跑什么");
});

test("workflow library: confirm guessed bindings, pass a trial, make it my workflow", async ({
  page,
}) => {
  const errors = trackConsoleErrors(page);
  await setUi(page, {});
  await openPage(page, "/models");
  const lib = page.getByRole("region", { name: "工作流库" });
  const wan = lib.getByRole("rowgroup", { name: "Wan 2.2 图生视频（社区）" });
  await lib.getByRole("button", { name: "展开 Wan 2.2 图生视频（社区）" }).click();
  await expect(wan.getByText("还有 3 项是导入时自动猜的，确认后才能试跑和登记。")).toBeVisible();
  await wan.getByRole("button", { name: "确认全部绑定" }).click();
  await expect(wan.getByText(/还有 \d+ 项是导入时自动猜的/)).toHaveCount(0);
  await wan.getByRole("tab", { name: "试跑" }).click();
  await wan.getByRole("button", { name: "试跑", exact: true }).click();
  await wan.getByRole("button", { name: "通过了，升为我的工作流" }).click({ timeout: 15_000 });
  await expect(wan.getByRole("row").first()).toContainText("我的工作流");
  expect(errors).toEqual([]);
});
