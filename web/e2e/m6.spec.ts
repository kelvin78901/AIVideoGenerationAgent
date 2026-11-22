/**
 * M6 on the Mock backend with the demo's QA scenario on (plan step 10b; `DRAMA_DEMO_QA=1`, its
 * own backend and data folder, VITE_DEMO_DATA=0): the demo's takes are checked as the app
 * starts (`studio/demo.py:DEMO_BAD_TAKES`), and once that and what it starts have settled:
 * 1. 生成 shows what QA did: 1-05 T1 (the note's writing drawn wrong) and 1-06 T1 (someone
 *    else's face) fail one check each, are not recommended and were rerun; 1-04 T4 failed only
 *    its mouths and got a 口型修复; the run log says so.
 * 2. A changed threshold judges the takes again: 1-06 T1 passes with the face limit lowered,
 *    and fails again after 恢复默认.
 * 3. 1-04 T1 adopted, then 口型修复 and 2K 精修: each makes one take, which is adopted in its
 *    turn (no worse than the adopted take it was made from).
 * Independent of the other projects (`tests/e2e/test_qa_loop.py` checks the same scenario
 * through the API, with the `model_call` rows).
 */
import { expect, test, type Page } from "@playwright/test";

import { note, openPage, setUi, settleJobs, trackContract } from "./fixtures";

test.describe.configure({ mode: "serial" });

const wallOf = (page: Page) => page.getByRole("list", { name: "候选" });
const takeOf = (page: Page, n: number) =>
  wallOf(page).getByRole("listitem", { name: `候选 T${n}`, exact: true });

async function openShot(page: Page, label: string): Promise<void> {
  await openPage(page, `/s/demo/e/1/generate?shot=demo-shot-${label}`);
  await expect(page.getByRole("heading", { name: `镜头 ${label} 的候选` })).toBeVisible();
}

test.beforeAll(async ({ request }) => {
  await settleJobs(request);
});

test("生成: the bad takes are held back, rerun or repaired, and the log says so", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const { errors, missing } = trackContract(page);
  await setUi(page, {});

  // 1-05: T1 drew the note's writing wrong; QA reran it, the rerun passes and is recommended.
  await openShot(page, "1-05");
  const bad = takeOf(page, 1);
  await expect(bad).toContainText("未过 1 项");
  await expect(bad).toContainText("画面文字");
  await expect(bad).toContainText("质检没过 → 已自动重跑");
  await expect(bad).not.toContainText("推荐");
  const rerun = takeOf(page, 2);
  await expect(rerun).toContainText("自动重跑");
  await expect(rerun).toContainText("推荐");
  await expect(rerun).not.toContainText("未过");
  // The episode's QA card counts both reruns (1-05's and 1-06's).
  await expect(page.getByRole("region", { name: "队列和质检" })).toContainText("已自动重跑 2 次");

  // 1-06: T1 has someone else's face; rerun the same way.
  await openShot(page, "1-06");
  await expect(takeOf(page, 1)).toContainText("未过 1 项");
  await expect(takeOf(page, 1)).toContainText("人脸一致性");
  await expect(takeOf(page, 1)).not.toContainText("推荐");
  await expect(takeOf(page, 2)).toContainText("推荐");

  // 1-04: T4 (the Seedance switch) is off only at the mouths, so it was lip-synced, not rerun:
  // T5 is the repair, passing; neither is adopted.
  await openShot(page, "1-04");
  const lips = takeOf(page, 4);
  await expect(lips).toContainText("只差口型");
  await expect(lips).toContainText("只差口型 → 已自动送去口型修复");
  await expect(lips).not.toContainText("推荐");
  const repaired = takeOf(page, 5);
  await expect(repaired).toContainText("只差口型，自动口型修复自 T4");
  await expect(repaired).not.toContainText("未过");
  await expect(wallOf(page)).not.toContainText("已采纳");

  const log = page.getByRole("region", { name: "运行记录" });
  await expect(log).toContainText(/出 T1 · 未过 1 项（画面文字）→ 自动重跑/);
  await expect(log).toContainText(/出 T1 · 未过 1 项（人脸一致性）→ 自动重跑/);
  await expect(log).toContainText(/出 T4 · 只有口型没过 → 自动口型修复/);
  note(missing);
  expect(errors).toEqual([]);
});

test("阈值: a lowered face limit passes 1-06 T1, 恢复默认 fails it again", async ({ page }) => {
  test.setTimeout(60_000);
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openShot(page, "1-06");
  const bad = takeOf(page, 1);
  await expect(bad).toContainText("未过 1 项");

  // The seeded face score is 0.1, under the default (0.18 since the step 5c calibration).
  const limit = page.getByRole("spinbutton", { name: "人脸一致性的阈值" });
  const before = await limit.inputValue();
  expect(Number(before)).toBeGreaterThan(0.1);
  await limit.fill("0.05");
  await limit.press("Enter");
  await expect(bad).not.toContainText("未过", { timeout: 15_000 });
  await expect(limit).toHaveValue("0.05");

  await page.getByRole("button", { name: "恢复默认" }).click();
  await expect(limit).toHaveValue(before);
  await expect(bad).toContainText("未过 1 项", { timeout: 15_000 });
  note(missing);
  expect(errors).toEqual([]);
});

test("口型修复 and 2K 精修 on the adopted take: one take each, adopted in turn", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openShot(page, "1-04");
  const pill = page
    .getByRole("region", { name: "镜头", exact: true })
    .getByRole("button", { name: /^1-04/ });

  await takeOf(page, 1).getByRole("button", { name: "采纳", exact: true }).click();
  await expect(page.getByText("1-04 采纳 T1。")).toBeVisible();
  // The pill reads the episode's take list, which may still be on its first fetch here
  // (api/queryClient.ts: that fetch is restarted, not reused).
  await expect(pill).toContainText("已采纳");

  // 局部修复 ▾ → 口型修复 on this machine: T6, from T1; it passes, so it replaces T1.
  await takeOf(page, 1).getByRole("button", { name: "局部修复" }).click();
  await page.getByRole("menuitem", { name: /^口型修复 本地/ }).click();
  await expect(page.getByText(/^已把 1-04 T1 送去口型修复（.+），本地跑，不计费。$/)).toBeVisible();
  const lip = takeOf(page, 6);
  await expect(lip).toContainText("口型修复自 T1", { timeout: 30_000 });
  await expect(lip).toContainText("已采纳", { timeout: 30_000 });
  await expect(takeOf(page, 1)).not.toContainText("已采纳");

  // 2K 精修 on T6: T7, from T6, adopted the same way.
  await lip.getByRole("button", { name: /^2K 精修 · / }).click();
  await expect(page.getByText(/^已把 1-04 T6 送去 2K 精修（.+）/)).toBeVisible();
  const up = takeOf(page, 7);
  await expect(up).toContainText("2K 精修自 T6", { timeout: 30_000 });
  await expect(up).toContainText("已采纳", { timeout: 30_000 });
  await expect(lip).not.toContainText("已采纳");
  await expect(pill).toContainText("已采纳");
  note(missing);
  expect(errors).toEqual([]);
});
