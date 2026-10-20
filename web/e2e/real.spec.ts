/**
 * The no-demo-data round (plan step 12, `VITE_DEMO_DATA=0`): the pages M2 put on the backend,
 * with nothing from MSW in between, so a response that does not match its zod contract shows up
 * here instead of behind the demo data. Endpoints of later milestones answer 404 (the page says
 * 加载失败 there); those are listed on the test, not failed.
 */
import { expect, test, type Page } from "@playwright/test";

import { openPage, setUi } from "./fixtures";

/** Contract violations (api/client.ts, api/events.ts), page crashes and server errors. */
function trackContract(page: Page): { errors: string[]; missing: Set<string> } {
  const errors: string[] = [];
  const missing = new Set<string>();
  page.on("console", (msg) => {
    const text = msg.text();
    if (msg.type() === "error" && /does not match its schema|\[events\] /.test(text)) {
      errors.push(text);
    }
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("response", (resp) => {
    const path = new URL(resp.url()).pathname;
    if (resp.status() >= 500) errors.push(`HTTP ${resp.status()} ${path}`);
    if (resp.status() === 404 && path.startsWith("/api/")) missing.add(path);
  });
  return { errors, missing };
}

function note(missing: Set<string>): void {
  for (const path of [...missing].sort()) {
    test.info().annotations.push({ type: "404 (later milestone)", description: path });
  }
}

const PAGES = [
  { id: "setup", path: "/setup" },
  { id: "spec", path: "/s/demo/spec" },
  { id: "novel", path: "/s/demo/e/1/novel" },
  { id: "script", path: "/s/demo/e/1/script" },
  { id: "script e2", path: "/s/demo/e/2/script" },
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
