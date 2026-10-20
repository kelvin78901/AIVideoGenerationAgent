/**
 * M2 flows on the Mock backend (plan step 12): a new series from the novel (confirmed before
 * 分集规划, step 12d) to a confirmed script (with one budget confirmation), the three choices on a confirmed script line, and an edit of
 * the confirmed demo novel synced down to the script. The demo tests change the demo series:
 * they run after the new series, the script line before the novel.
 */
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { openPage, setUi, trackConsoleErrors } from "./fixtures";

const NOVEL = fileURLToPath(new URL("../../tests/fixtures/demo/雨停之前.txt", import.meta.url));
const WRITE = { "X-Drama-Studio": "1" };
// Built in M3 (assets) and M4 (shots): outside the demo series they are not there yet.
const LATER = [/\/api\/v1\/episodes\/[^/]+\/shots$/, /\/api\/v1\/series\/[^/]+\/assets$/];

test.describe.configure({ mode: "serial" });

const step = (page: Page, name: string) =>
  page.getByRole("navigation", { name: "制作步骤" }).getByRole("link", { name: new RegExp(name) });

/** Console errors, less the 404s of what later milestones build (each one checked). */
function trackErrors(page: Page): () => string[] {
  const errors = trackConsoleErrors(page);
  const missing: string[] = [];
  page.on("response", (resp) => {
    if (resp.status() === 404) missing.push(new URL(resp.url()).pathname);
  });
  return () => [
    ...errors.filter((e) => !e.includes("status of 404")),
    ...missing.filter((path) => !LATER.some((re) => re.test(path))).map((p) => `404 ${p}`),
  ];
}

/** Runs the run bar's product and waits for its first version. */
async function runFirst(page: Page): Promise<void> {
  await page.getByRole("button", { name: /^重跑 (≈|免费)/ }).click();
  await expect(page.getByRole("button", { name: "历史 1" })).toBeVisible({ timeout: 20_000 });
}

test("a new series: import, confirm the novel, plan and script episode 1", async ({ page }) => {
  test.setTimeout(120_000);
  const errors = trackErrors(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/novel");

  // 新建剧集 → 成片规格.
  await page.getByRole("banner").getByRole("button", { name: "《雨停之前》" }).click();
  await page.getByRole("menuitem", { name: "新建剧集…" }).click();
  const create = page.getByRole("dialog", { name: "新建剧集" });
  await create.getByLabel("剧名").fill("雨停之前 · 端到端");
  await create.getByRole("button", { name: "创建，去定成片规格" }).click();
  await expect(page).toHaveURL(/\/s\/[^/]+\/spec$/);
  const series = /\/s\/([^/]+)\/spec$/.exec(page.url())?.[1] ?? "";

  // 小说: import, with the rights confirmation.
  await step(page, "小说").click();
  await expect(page.getByText("还没有导入小说")).toBeVisible();
  await page.getByRole("button", { name: "导入小说" }).first().click();
  const dialog = page.getByRole("dialog", { name: "导入小说" });
  await dialog.getByTestId("novel-file").setInputFiles(NOVEL);
  await expect(dialog.getByText("识别到 3 章 · 3006 字")).toBeVisible();
  await dialog.getByRole("checkbox", { name: /改编权/ }).click();
  await dialog.getByRole("button", { name: "导入" }).click();
  await expect(page.getByText("已导入 雨停之前.txt：3 章 · 3006 字")).toBeVisible();

  // 补全 → 全部采纳 → 设定提取 (it reads the adopted additions).
  await expect(page.getByRole("button", { name: "小说补全", pressed: true })).toBeVisible();
  await runFirst(page);
  await page.getByRole("button", { name: "全部采纳" }).click();
  await expect(page.getByText("已采纳全部未忽略的建议。")).toBeVisible();
  await page.getByRole("button", { name: "设定提取", exact: true }).click();
  await runFirst(page);

  // 确认原文 before there are episodes (the gate is the series'): on to 剧本 and its 分集规划.
  await page.getByRole("button", { name: "确认原文，生成剧本" }).click();
  await expect(page).toHaveURL(new RegExp(`/s/${series}/e/1/script$`));
  await expect(step(page, "小说")).toContainText("已确认");

  // 剧本: 分集规划, then episode 1's script over the per-call cap (asks first).
  await page.getByRole("button", { name: "开始分集规划" }).click();
  await expect(page.getByRole("link", { name: /第 1 集/ }).first()).toBeVisible({
    timeout: 20_000,
  });
  const override = { scope: "component", scope_id: null, component_id: "script" };
  const capped = await page.request.put("/api/v1/config/override", {
    headers: WRITE,
    data: { ...override, data: { per_call_cap_usd: 0.00001 } },
  });
  expect(capped.ok()).toBe(true);
  await page.getByRole("button", { name: "生成这一集的剧本" }).click();
  const ask = page.getByRole("dialog", { name: "「剧本化」要你点头才会开始" });
  await expect(ask).toContainText("超过了这一步的单次上限");
  await ask.getByRole("button", { name: /^确认，开始运行/ }).click();
  await expect(page.getByRole("heading", { name: "第 1 集剧本" })).toBeVisible({
    timeout: 20_000,
  });
  const removed = await page.request.delete("/api/v1/config/override", {
    headers: WRITE,
    params: { scope: "component", component_id: "script" },
  });
  expect(removed.ok()).toBe(true);

  // Episode 1's script gate; the novel's shows on the episode too.
  await page.getByRole("button", { name: "确认剧本，分析素材" }).click();
  await expect(page).toHaveURL(new RegExp(`/s/${series}/e/1/assets$`));
  await expect(step(page, "小说")).toContainText("已确认");
  await expect(step(page, "剧本")).toContainText("已确认");
  expect(errors()).toEqual([]);
});

test("a confirmed script line: 撤销, 只改这里, 确认并同步", async ({ page }) => {
  const errors = trackErrors(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/script");
  await expect(step(page, "剧本")).toContainText("已确认");
  const block = (text: RegExp) => page.getByRole("button", { name: text, pressed: false });
  const edit = async (from: RegExp, to: string) => {
    await block(from).click();
    await page.getByRole("button", { name: "编辑" }).click();
    await page.getByLabel("编辑这一段（保存后会显示影响范围）").fill(to);
    await page.getByRole("button", { name: "保存" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("已确认的第 1 集剧本会改成新内容");
    return dialog;
  };

  // 撤销: nothing written.
  let dialog = await edit(/门口靠着一把红色长柄伞/, "门口靠着一把红伞。");
  await dialog.getByRole("button", { name: "撤销" }).click();
  await expect(dialog).toBeHidden();
  await page.reload();
  await expect(page.getByRole("button", { name: /门口靠着一把红色长柄伞/ })).not.toContainText(
    "已修改",
  );

  // 只改这里: written, the gate stays confirmed.
  dialog = await edit(/门口靠着一把红色长柄伞/, "门口靠着一把红伞。");
  await dialog.getByRole("button", { name: "只改这里，下游标待更新" }).click();
  await expect(dialog).toBeHidden();
  await page.reload();
  await expect(page.getByRole("button", { name: /门口靠着一把红伞。/ })).toContainText("已修改");
  await expect(step(page, "剧本")).toContainText("已确认");

  // 确认并同步: written, and the sync starts.
  dialog = await edit(/周屿？/, "……是你啊。");
  await dialog.getByRole("button", { name: /^确认并同步 · 预计/ }).click();
  await expect(page.getByText(/^已开始同步/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: /……是你啊。/ })).toContainText("已修改");
  expect(errors()).toEqual([]);
});

test("an edit of the confirmed novel syncs down to the script", async ({ page }) => {
  test.setTimeout(90_000);
  const errors = trackErrors(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/novel");
  await expect(step(page, "小说")).toContainText("已确认");
  await page.getByRole("radio", { name: "原文" }).click();
  await page.getByRole("button", { name: "改第 2 段" }).click();
  await page.getByLabel("第 2 段的文字").fill("家门口靠着一把红伞，伞尖还在滴水。");
  await page.getByRole("button", { name: "保存" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("已确认的小说原文会改成新内容");
  await dialog.getByRole("button", { name: /^确认并同步 · 预计/ }).click();
  await expect(page.getByText(/^已开始同步/)).toBeVisible();
  await expect(page.getByText(/^已同步：\d+ 个产物更新/)).toBeVisible({ timeout: 60_000 });
  // Both gates reopened: the new content is the model's, to confirm again.
  await expect(step(page, "小说")).not.toContainText("已确认");
  await expect(step(page, "剧本")).not.toContainText("已确认");

  await step(page, "剧本").click();
  await expect(page.getByText(/^当前产物 · 第 1 集剧本/)).toBeVisible();
  // The sync's rerun (the script's primary model), adopted over the hand edits before it.
  await expect(page.getByText(/^v\d+ · DeepSeek V4 Pro · API · .+ · 已采纳$/)).toBeVisible();
  await expect(page.getByRole("button", { name: "确认剧本，分析素材" })).toBeEnabled();
  expect(errors()).toEqual([]);
});
