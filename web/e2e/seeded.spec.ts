/**
 * Tests that need the demo as the backend seeds it (VITE_DEMO_DATA=0, like real.spec.ts). The
 * M2 flows (m2.spec.ts) re-script episode 1 with Mock output, so this project runs first: the
 * `smoke` project depends on it (playwright.config.ts).
 */
import { expect, test } from "@playwright/test";

import { note, openPage, setUi, trackContract } from "./fixtures";

test("dialogue audio: 全部配音 on the backend; the lines play on the script page", async ({
  page,
}) => {
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/assets");
  await expect(page.getByText(/^台词配音 \d \/ 2$/)).toBeVisible();
  const all = page.getByRole("button", { name: "全部配音" });
  // A retry finds them dubbed already.
  if (await all.isEnabled()) {
    await all.click();
    const dialog = page.getByRole("dialog", { name: "给第 1 集配音" });
    await expect(dialog).toContainText(/要配 2 句台词，约 \$/);
    await dialog.getByRole("button", { name: "开始配音" }).click();
  }
  // Each take arrives over SSE (`product.updated`, slot `line_audio`).
  await expect(page.getByText("台词配音 2 / 2")).toBeVisible({ timeout: 30_000 });
  await openPage(page, "/s/demo/e/1/script");
  await expect(page.getByRole("button", { name: "播放：……周屿？" })).toBeVisible();
  await expect(page.getByText(/^台词 \d+\.\d 秒 · 已配音 1 \/ 1$/)).toHaveCount(2);
  // The audio is the backend's file.
  const dub = await (await page.request.get("/api/v1/episodes/demo-e1/dub")).json();
  const file = await page.request.get(`/api/v1/files/${dub.lines[0].audio.sha256}`);
  expect(file.status()).toBe(200);
  expect(file.headers()["content-type"]).toBe("audio/wav");
  note(missing);
  expect(errors).toEqual([]);
});
