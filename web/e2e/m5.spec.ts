/**
 * M5 on the Mock backend (plan step 13d; VITE_DEMO_DATA=0): 生成 from the storyboard `m4`
 * confirmed — 1-05's first run makes two local takes, one adopted, dropped and the other
 * adopted, 「用 API 出终版」 makes its 2K final and the header's spend follows; 生成确认 refuses
 * while shots are open, then (the others adopted through the API) locks them and is reopened.
 * The models page: a community workflow imported from ComfyUI, its node pack installed after a
 * snapshot, a trial, 「我的工作流」; a bad node pack breaks it, the check says so and rolls back.
 * Runs after `m4` and before `real` and `smoke`; it leaves a fresh, unscanned sample PC behind.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { note, openPage, setUi, trackContract } from "./fixtures";

test.describe.configure({ mode: "serial" });

const WRITE = { "X-Drama-Studio": "1" };
const EP = "demo-e1";

interface Version {
  id: string;
  job_id: string | null;
}
interface Job {
  id: string;
  state: string;
}

async function get<T>(request: APIRequestContext, path: string): Promise<T> {
  const resp = await request.get(`/api/v1${path}`);
  expect(resp.ok(), `GET ${path}`).toBe(true);
  return (await resp.json()) as T;
}

async function send<T>(request: APIRequestContext, path: string, data?: unknown): Promise<T> {
  const resp = await request.post(`/api/v1${path}`, { headers: WRITE, data });
  expect(resp.ok(), `POST ${path}: ${await resp.text()}`).toBe(true);
  return (await resp.json()) as T;
}

/** Waits for a job to end; one waiting for a yes (over a cap) gets it. */
async function finish(request: APIRequestContext, job: Job): Promise<void> {
  const ended = async () => (await get<Job>(request, `/jobs/${job.id}`)).state;
  await expect
    .poll(ended, { timeout: 30_000 })
    .toMatch(/^(succeeded|failed|canceled|waiting_confirm)$/);
  if ((await ended()) === "waiting_confirm") await send(request, `/jobs/${job.id}/confirm`);
  await expect.poll(ended, { timeout: 30_000 }).toBe("succeeded");
}

const videoOf = async (request: APIRequestContext, label: string) => {
  const shots = await get<{ label: string; video_product_id: string }[]>(
    request,
    `/episodes/${EP}/shots`,
  );
  const shot = shots.find((s) => s.label === label);
  if (!shot) throw new Error(`no shot ${label}`);
  return get<{ id: string; versions: Version[] }>(request, `/products/${shot.video_product_id}`);
};

/** The header's 「已花 $x」. */
async function spent(page: Page): Promise<number> {
  const text = (await page.getByTestId("spend").locator("b").textContent()) ?? "";
  return Number(text.replace(/[^\d.]/g, ""));
}

test("生成: takes for a shot, adopt and drop, the API final, then 生成确认", async ({ page }) => {
  test.setTimeout(120_000);
  const { errors, missing } = trackContract(page);
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/generate?shot=demo-shot-1-05");
  await expect(page.getByRole("heading", { name: "镜头 1-05 的候选" })).toBeVisible();
  const pill = page.getByRole("region", { name: "镜头" }).getByRole("button", { name: /^1-05/ });
  await expect(pill).toContainText("未开始");
  await expect.poll(() => spent(page)).toBeGreaterThan(0);
  const before = await spent(page);

  // The first run: the rule's two local takes, over SSE.
  await page.getByRole("button", { name: /再出一条/ }).click();
  const wall = page.getByRole("list", { name: "候选" });
  const take = (n: number) => wall.getByRole("listitem", { name: `候选 T${n}` });
  await expect(take(2)).toBeVisible({ timeout: 30_000 });
  await expect(take(1)).toContainText("（本地）");
  await expect(take(1)).toContainText("未检查");

  // Adopt T1, drop it, adopt T2.
  await take(1).getByRole("button", { name: "采纳", exact: true }).click();
  await expect(page.getByText("1-05 采纳 T1。")).toBeVisible();
  await expect(pill).toContainText("已采纳");
  await take(1).getByRole("button", { name: "取消采纳" }).click();
  await expect(page.getByText("已取消采纳 1-05 T1。")).toBeVisible();
  await expect(pill).not.toContainText("已采纳");
  await take(2).getByRole("button", { name: "采纳", exact: true }).click();
  await expect(page.getByText("1-05 采纳 T2。")).toBeVisible();

  // 「用 API 出终版」 at the card's price: T3, H3 Regenerate-2K at 2K; the spend goes up.
  await take(2)
    .getByRole("button", { name: /^用 API 出终版 · 约 \$/ })
    .click();
  await expect(page.getByText("已开始出 1-05 T2 的 2K 终版（API）。")).toBeVisible();
  await expect(take(3)).toContainText("H3 Regenerate-2K", { timeout: 30_000 });
  await expect(take(3)).toContainText("混合模式出终版");
  await expect.poll(() => spent(page), { timeout: 15_000 }).toBeGreaterThan(before);
  await take(3).getByRole("button", { name: "采纳", exact: true }).click();
  await expect(page.getByText("1-05 采纳 T3。")).toBeVisible();
  const log = page.getByRole("region", { name: "运行记录" });
  await expect(log.getByRole("listitem").first()).toContainText("1-05");
  await expect(log).toContainText("用 API 出终版 → H3 Regenerate-2K 出 T3");

  // 生成确认 with shots still open: refused, it says which.
  await page.getByRole("button", { name: "去后期" }).click();
  await expect(page.getByText(/^还有 5 个镜头没采纳视频：1-04、1-06/)).toBeVisible();
  await expect(page).toHaveURL(/\/generate/);

  // The rest through the API, one take each: 1-04 again (`m4` gave it a new first frame, so
  // the seeded takes are out of date), and in order (1-08 continues 1-06's last frame, 1-09
  // 1-08's).
  const { request } = page;
  for (const label of ["1-04", "1-06", "1-07", "1-08", "1-09"]) {
    const product = await videoOf(request, label);
    const job = await send<Job>(request, `/products/${product.id}/run`, { mode: "run", count: 1 });
    await finish(request, job);
    const made = (await videoOf(request, label)).versions.find((v) => v.job_id === job.id);
    if (!made) throw new Error(`no take for ${label}`);
    await send(request, `/versions/${made.id}/adopt`);
  }

  // 生成确认: on to 后期; the step is confirmed, and can be reopened.
  await page.reload();
  await expect(page.locator("[data-loading]")).toHaveCount(0, { timeout: 15_000 });
  const pills = page
    .getByRole("region", { name: "镜头", exact: true })
    .getByRole("button", { name: /^1-0\d/ });
  await expect(pills).toHaveCount(9);
  for (const p of await pills.all()) await expect(p).toContainText("已采纳");
  const nav = page.getByRole("navigation", { name: "制作步骤" });
  await expect(nav.getByRole("link", { name: /生成/ })).toContainText("9/9");
  // Locking nine products announces each one; slow CI machines take a few seconds.
  await page.getByRole("button", { name: "去后期" }).click();
  await expect(page).toHaveURL(/\/s\/demo\/e\/1\/post$/, { timeout: 20_000 });
  await expect(nav.getByRole("link", { name: /生成/ })).toContainText("已确认");
  await page.goBack();
  await page.getByRole("button", { name: "重新打开" }).click();
  await expect(page.getByText("已重新打开这一步，改完后需要再确认。")).toBeVisible({
    timeout: 20_000,
  });
  await expect(nav.getByRole("link", { name: /生成/ })).toContainText("9/9");
  note(missing);
  expect(errors).toEqual([]);
});

test("models: a community workflow installed, tried and mine; a bad pack rolled back", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { errors, missing } = trackContract(page);
  const { request } = page;
  // Installing needs the scanned sample PC (its ComfyUI).
  await send(request, "/setup/scan");
  await expect
    .poll(async () => (await get<{ phase: string }>(request, "/setup/profile")).phase, {
      timeout: 30_000,
    })
    .toBe("scanned");

  await setUi(page, {});
  await openPage(page, "/models");
  const lib = page.getByRole("region", { name: "工作流库" });
  const importFile = async (path: string, name: string) => {
    await lib.getByRole("button", { name: "导入工作流" }).click();
    const dialog = page.getByRole("dialog", { name: "导入工作流" });
    await dialog
      .getByRole("listitem", { name: path })
      .getByRole("button", { name: "导入" })
      .click();
    await expect(page.getByText(`已导入「${name}」：先确认绑定，再试跑`)).toBeVisible();
    await expect(dialog).toBeHidden();
    return lib.getByRole("rowgroup", { name });
  };
  const install = async (row: ReturnType<typeof lib.getByRole>) => {
    await row.getByRole("tab", { name: "体检" }).click();
    await row.getByRole("button", { name: "安装缺的 1 个节点包" }).click();
    const ask = page.getByRole("alertdialog", { name: "开始安装前请确认" });
    await expect(ask.getByText("会改动你的 ComfyUI（1 项）")).toBeVisible();
    await ask.getByRole("button", { name: "确认，开始安装" }).click();
    await expect(page.getByText(/^已存快照 .+，装好了 1 个节点包$/)).toBeVisible();
  };

  // 图生视频-wan22: guessed bindings confirmed, VHS installed, a trial, 我的工作流.
  const WAN = "图生视频-wan22";
  const wan = await importFile("社区/图生视频-wan22.json", WAN);
  const head = wan.getByRole("row").first();
  await expect(head).toContainText("未验证");
  await expect(wan.getByText(/还有 \d+ 项是导入时自动猜的/)).toBeVisible();
  await wan.getByRole("button", { name: "确认全部绑定" }).click();
  await expect(wan.getByText(/还有 \d+ 项是导入时自动猜的/)).toHaveCount(0);
  await install(wan);
  await expect(head).toContainText("正常");
  await wan.getByRole("tab", { name: "试跑" }).click();
  await wan.getByRole("button", { name: "试跑", exact: true }).click();
  await wan.getByRole("button", { name: "通过了，升为我的工作流" }).click({ timeout: 20_000 });
  await expect(head).toContainText("我的工作流");

  // 胶片颗粒-filmgrain's pack takes KSampler away: wan22 worked, and now points back to the
  // snapshot taken before; rolling back brings it back.
  const grain = await importFile("社区/胶片颗粒-filmgrain.json", "胶片颗粒-filmgrain");
  await install(grain);
  await expect(head).toContainText("有问题 2 处");
  const expand = wan.getByRole("button", { name: `展开 ${WAN}` });
  if ((await expand.getAttribute("aria-expanded")) !== "true") await expand.click();
  await wan.getByRole("tab", { name: "体检" }).click();
  const problems = wan.getByRole("list", { name: "问题" });
  await expect(problems).toContainText("节点类 KSampler 在 ComfyUI 里找不到");
  await expect(problems).toContainText("上次装节点包之前是好的，装完坏了");
  await wan.getByRole("button", { name: "回滚到这次安装前的快照" }).click();
  await wan
    .getByRole("group", { name: "回滚到这次安装前的快照" })
    .getByRole("button", { name: "确认回滚" })
    .click();
  await expect(page.getByText(/^已排上回滚到 /)).toBeVisible();
  await expect(head).toContainText("正常");
  await expect(head).toContainText("我的工作流");

  // Back to a fresh sample PC (no scan, no snapshots), as the later projects expect.
  await send(request, "/dev/setup/machine", { machine: "pc" });
  note(missing);
  expect(errors).toEqual([]);
});
