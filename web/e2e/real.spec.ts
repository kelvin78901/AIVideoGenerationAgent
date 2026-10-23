/**
 * The no-demo-data round (plan step 12, `VITE_DEMO_DATA=0`): the pages M2–M4 put on the
 * backend, with nothing from MSW in between, so a response that does not match its zod contract
 * shows up here instead of behind the demo data. Endpoints of later milestones answer 404 (the
 * page says 加载失败 there); those are listed on the test, not failed.
 */
import { expect, test } from "@playwright/test";

import { note, openPage, setUi, trackContract } from "./fixtures";

const PAGES = [
  { id: "setup", path: "/setup" },
  { id: "spec", path: "/s/demo/spec" },
  { id: "novel", path: "/s/demo/e/1/novel" },
  { id: "script", path: "/s/demo/e/1/script" },
  { id: "script e2", path: "/s/demo/e/2/script" },
  { id: "assets", path: "/s/demo/e/1/assets" },
  { id: "storyboard", path: "/s/demo/e/1/storyboard" },
  { id: "models", path: "/models" },
  { id: "dev jobs", path: "/dev/jobs" },
];

for (const p of PAGES) {
  test(`${p.id} reads the backend without contract errors`, async ({ page }) => {
    const { errors, missing } = trackContract(page);
    await setUi(page, {});
    await openPage(page, p.path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByTestId("demo-badge")).toHaveCount(0);
    note(missing);
    expect(errors).toEqual([]);
  });
}

test("novel: views, chapters, the bible, history and the prompt", async ({ page }) => {
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/novel");
  for (const view of ["采纳后", "对比", "原文"]) {
    await page.getByRole("radio", { name: view }).click();
  }
  await page.getByRole("combobox", { name: "章节" }).selectOption("1");
  // Numbered across the book: chapter 2 starts after chapter 1's five paragraphs.
  await expect(page.getByRole("button", { name: "第 6 段在剧本里的位置" })).toBeVisible();
  await page.getByRole("button", { name: "设定提取", exact: true }).click();
  await expect(page.getByText(/^当前产物 · 设定卡/)).toBeVisible();
  await page.getByRole("button", { name: /^历史 \d+$/ }).click();
  await expect(page.getByRole("tab", { name: /^历史 \d+$/, selected: true })).toBeVisible();
  await page.getByRole("button", { name: "改提示词" }).click();
  await expect(page.getByRole("tab", { name: "提示词", selected: true })).toBeVisible();
  note(missing);
  expect(errors).toEqual([]);
});

test("script: the beat board, the table, the plan and its history", async ({ page }) => {
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/script");
  await page.getByRole("radio", { name: "节拍看板" }).click();
  await page.getByRole("radio", { name: "结构化表格" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await page.getByRole("button", { name: "分集规划", exact: true }).click();
  await expect(page.getByText(/^当前产物 · 分集方案/)).toBeVisible();
  await page.getByRole("button", { name: /^历史 \d+$/ }).click();
  await expect(page.getByRole("tab", { name: /^历史 \d+$/, selected: true })).toBeVisible();
  note(missing);
  expect(errors).toEqual([]);
});

test("assets: real candidate pictures, the matrix, lock and unlock", async ({ page }) => {
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/assets");
  const list = page.getByRole("region", { name: "素材清单" });
  await list.getByRole("button", { name: /林晚出租屋/ }).click();
  const cands = page.getByRole("radiogroup", { name: "候选" });
  const first = cands.getByRole("img", { name: "v1 · A" });
  await expect(first).toBeVisible();
  // The picture is the backend's Mock file, really loaded.
  await expect
    .poll(() => first.evaluate((img) => (img as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await page.getByRole("radio", { name: "出场矩阵" }).click();
  await expect(page.getByRole("table", { name: "出场矩阵" })).toBeVisible();
  await page.getByRole("radio", { name: "清单" }).click();
  await cands.getByRole("radio", { name: "v1 · B" }).click();
  await page.getByRole("button", { name: "锁定为参考" }).click();
  await expect(list.getByRole("button", { name: /林晚出租屋/ })).toContainText("已锁定");
  // The shots of scene 2 use it as a reference (M4): unlocking previews them first.
  await page.getByRole("button", { name: "解锁" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("1-06、1-08，共 2 个镜头用它做参考");
  await dialog.getByRole("button", { name: "只改这里，下游标待更新" }).click();
  await expect(list.getByRole("button", { name: /林晚出租屋/ })).toContainText("待选");
  note(missing);
  expect(errors).toEqual([]);
});

test("on-screen text: the backend's OCR check, a mismatch asks before locking", async ({
  page,
}) => {
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/assets");
  const note1 = page
    .getByRole("region", { name: "素材清单" })
    .getByRole("button", { name: /便利贴手写/ });
  await note1.click();
  const cands = page.getByRole("radiogroup", { name: "候选" });
  const b = cands.getByRole("radio", { name: "v1 · B" });
  await expect(b).toContainText("OCR 不一致：有错字");
  await expect(cands.getByRole("radio", { name: "v1 · A" })).toContainText("OCR 一致");
  await expect
    .poll(() => b.getByRole("img").evaluate((img) => (img as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await b.click();
  // The pick is saved before locking, or the lock takes the candidate picked before.
  await expect(b).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "锁定为参考" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("候选 B 的字和要求不一致");
  await expect(dialog).toContainText("OCR 读出来是「楼下便利店，等你到十二占。」");
  await dialog.getByRole("button", { name: "取消" }).click();
  await expect(dialog).toBeHidden();
  await expect(note1).toContainText("待选");
  note(missing);
  expect(errors).toEqual([]);
});

test("assets gate and a locked asset's edit, on the backend", async ({ page }) => {
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/assets");
  await page.getByRole("button", { name: "去做分镜" }).click();
  await expect(page.getByText(/^还有 \d+ 条素材没锁定：/)).toBeVisible();
  await expect(page).toHaveURL(/\/assets$/);
  // 林晚 (locked) is selected first: a new description shows the impact first.
  const desc = page.getByLabel("描述（就是这条素材的提示词意图层）");
  await desc.fill("二十六岁，齐耳短发。");
  await desc.blur();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("「林晚」已锁定，改动会影响下游");
  await expect(dialog).toContainText("「林晚」按新的设置重新出候选");
  await expect(dialog).toContainText("出现在场 1、2");
  await dialog.getByRole("button", { name: "撤销" }).click();
  await expect(dialog).toBeHidden();
  await expect(desc).not.toHaveValue("二十六岁，齐耳短发。");
  note(missing);
  expect(errors).toEqual([]);
});
