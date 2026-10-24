/**
 * M4 on the Mock backend (plan step 8; VITE_DEMO_DATA=0, the storyboard is the backend's): the
 * demo episode's animatic plays its dubbed lines (`seeded` dubbed them), then shot 1-04 is picked,
 * finished on the API model and confirmed, the other shots too, and 分镜确认. Runs after
 * `seeded` and before `real` and `smoke`, which find the storyboard confirmed.
 */
import { expect, test, type Page } from "@playwright/test";

import { note, openPage, setUi, trackContract } from "./fixtures";

test.describe.configure({ mode: "serial" });

/** Every clip the page starts playing, in order. */
async function recordPlays(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { played: string[] };
    w.played = [];
    const play = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (this: HTMLMediaElement) {
      w.played.push(this.src);
      return play.call(this);
    };
  });
}

const played = (page: Page) =>
  page.evaluate(() => (window as unknown as { played: string[] }).played);

test("the animatic plays the episode with its dubbed lines", async ({ page }) => {
  const { errors, missing } = trackContract(page);
  await recordPlays(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/storyboard");
  const preview = page.getByRole("region", { name: "预演" });
  // The cards show the picked keyframes: the backend's files, really loaded.
  const card = page
    .getByRole("region", { name: "镜头列表" })
    .getByRole("button", { name: /^1-04/ });
  await expect
    .poll(() => card.locator("img").evaluate((img) => (img as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await expect(preview).not.toContainText("句还没配音");

  // Jump to 1-04, play: its line sounds 0.3 s in, under its subtitle.
  await preview.getByRole("button", { name: /^镜头 1-04，/ }).click({ position: { x: 2, y: 8 } });
  await expect(page.getByTestId("preview-clock")).toHaveText(/^00:10 \//);
  await preview.getByRole("button", { name: "播放预演" }).click();
  await expect(page.getByTestId("preview-subtitle")).toHaveText("……周屿？");
  const dub = await (await page.request.get("/api/v1/episodes/demo-e1/dub")).json();
  const line = dub.lines.find((x: { line_id: string }) => x.line_id === "demo-b5");
  await expect.poll(() => played(page)).toEqual([expect.stringContaining(line.audio.sha256)]);

  // Space pauses (when no control has the focus) and selects the shot it stopped in.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Space");
  await expect(preview.getByRole("button", { name: "播放预演" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^镜头 1-0[45]$/ })).toBeVisible();
  note(missing);
  expect(errors).toEqual([]);
});

test("a shot picked, finished on the API and confirmed; every shot, then 分镜确认", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/storyboard?shot=demo-shot-1-04");
  const frames = page.getByRole("radiogroup", { name: "首帧" });
  const b = frames.getByRole("radio", { name: "v1 · B" });
  await b.click();
  await expect(b).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: /^用 API 出终版/ }).click();
  // The final arrives over SSE: one picture, made from B on the API model.
  const final = frames.getByRole("radio", { name: "v2 · A" });
  await expect(final).toBeVisible({ timeout: 20_000 });
  await expect(final).toContainText("API 终版");
  await page.getByRole("button", { name: "确认这个镜头" }).click();
  await expect(page.getByRole("button", { name: "取消确认" })).toBeVisible();

  const cards = page.getByRole("region", { name: "镜头列表" });
  for (const label of ["1-05", "1-06", "1-07", "1-08", "1-09"]) {
    await cards.getByRole("button", { name: new RegExp(`^${label}`) }).click();
    await expect(page.getByRole("heading", { name: `镜头 ${label}` })).toBeVisible();
    await page.getByRole("button", { name: "确认这个镜头" }).click();
    await expect(page.getByRole("button", { name: "取消确认" })).toBeVisible();
  }
  const nav = page.getByRole("navigation", { name: "制作步骤" });
  await expect(nav.getByRole("link", { name: /分镜/ })).toContainText("9/9");

  // 分镜确认, on to 生成.
  await page.getByRole("button", { name: "去生成视频" }).click();
  await expect(page).toHaveURL(/\/s\/demo\/e\/1\/generate$/);
  await expect(nav.getByRole("link", { name: /分镜/ })).toContainText("已确认");
  note(missing);
  expect(errors).toEqual([]);
});
