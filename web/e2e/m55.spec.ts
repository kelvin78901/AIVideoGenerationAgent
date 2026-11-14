/**
 * M5.5 on the Mock backend (plan step 17; VITE_DEMO_DATA=0), the milestone's two acceptance
 * flows on the storyboard `m4` confirmed and `m5` generated from:
 * 1. 1-04: a 4:3 picture uploaded as its first frame, cut to 9:16 in the crop dialog, the shot
 *    confirmed (that locks it); the take made next starts from exactly that picture.
 * 2. 1-05: its locked first frame redrawn, inpainted and upscaled, one new candidate each; the
 *    original is still in 历史 (设为当前 brings it back), and confirming locks it again.
 * Each ends with 分镜确认 again. Runs after `m5` and before `real` and `smoke`.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { note, openPage, setUi, trackContract } from "./fixtures";

test.describe.configure({ mode: "serial" });

const WRITE = { "X-Drama-Studio": "1" };
const EP = "demo-e1";

interface File {
  role: string;
  sha256: string;
  w?: number | null;
  h?: number | null;
}
interface Version {
  id: string;
  job_id: string | null;
  origin: string;
  parent_version_id: string | null;
  files: File[];
  params: { request?: { first_frame?: string } };
}
interface Product {
  id: string;
  versions: Version[];
}
interface Shot {
  id: string;
  label: string;
  keyframe_product_id: string | null;
  keyframe_sha256: string | null;
  video_product_id: string;
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

async function shotOf(request: APIRequestContext, label: string): Promise<Shot> {
  const shots = await get<Shot[]>(request, `/episodes/${EP}/shots`);
  const shot = shots.find((s) => s.label === label);
  if (!shot) throw new Error(`no shot ${label}`);
  return shot;
}

async function keyframeOf(request: APIRequestContext, label: string): Promise<Product> {
  const shot = await shotOf(request, label);
  if (!shot.keyframe_product_id) throw new Error(`${label} has no keyframe`);
  return get<Product>(request, `/products/${shot.keyframe_product_id}`);
}

const candidates = (v: Version) => v.files.filter((f) => f.role === "candidate");

/** The demo starts with every shot confirmed; a confirmed shot's first frame takes no change. */
async function unconfirm(request: APIRequestContext, label: string): Promise<void> {
  const resp = await request.patch(`/api/v1/shots/demo-shot-${label}`, {
    data: { confirmed: false },
    headers: WRITE,
  });
  expect(resp.ok(), `unconfirm ${label}: ${await resp.text()}`).toBe(true);
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

/** A `w × h` PNG drawn in the page: a phone photo's 4:3, not the series' 9:16. */
async function photo(page: Page, w: number, h: number): Promise<Buffer> {
  const data = await page.evaluate(
    ({ width, height }) => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("no 2d canvas");
      ctx.fillStyle = "#2a5d8f";
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#e8c547";
      ctx.fillRect(width / 2 - 60, 0, 120, height); // a stripe down the middle the crop keeps
      return canvas.toDataURL("image/png").split(",")[1] ?? "";
    },
    { width: w, height: h },
  );
  return Buffer.from(data, "base64");
}

/** 分镜确认: every shot confirmed again, on to 生成 (the later projects expect it confirmed). */
async function confirmBoard(page: Page): Promise<void> {
  const nav = page.getByRole("navigation", { name: "制作步骤" });
  await expect(nav.getByRole("link", { name: /分镜/ })).toContainText("9/9");
  await page.getByRole("button", { name: "去生成视频" }).click();
  await expect(page).toHaveURL(/\/s\/demo\/e\/1\/generate$/);
  await expect(nav.getByRole("link", { name: /分镜/ })).toContainText("已确认");
}

async function openSource(page: Page) {
  await page.getByRole("button", { name: "换来源" }).click();
  return page.getByRole("menu");
}

test("an uploaded 4:3 picture, cut to 9:16 and locked, is the take's first frame", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { errors, missing } = trackContract(page);
  const { request } = page;
  await unconfirm(request, "1-04");
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/storyboard?shot=demo-shot-1-04");
  await expect(page.getByRole("heading", { name: "镜头 1-04" })).toBeVisible();
  const frames = page.getByRole("radiogroup", { name: "首帧" });

  // 换来源 → 上传图片…: the file chooser, then the crop dialog with the picture as it is.
  const chooser = page.waitForEvent("filechooser");
  await (await openSource(page)).getByRole("menuitem", { name: /上传图片…/ }).click();
  await (
    await chooser
  ).setFiles({ name: "phone.png", mimeType: "image/png", buffer: await photo(page, 2400, 1800) });
  const dialog = page.getByRole("dialog", { name: "上传首帧 · 镜头 1-04" });
  await expect(dialog).toContainText("原图 2400×1800");
  await expect(dialog).toContainText(/成片 9:16 → 裁出 \d+×1800 → 缩到 1080×1920/);
  await dialog.getByRole("button", { name: "上传为候选" }).click();
  await expect(page.getByText("已上传为镜头 1-04 的新候选，并选中了它。")).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect(frames.getByRole("radio", { checked: true })).toContainText("上传 · phone.png");

  // The upload is one candidate at the delivery size, picked.
  const uploaded = (await keyframeOf(request, "1-04")).versions.at(-1);
  if (!uploaded) throw new Error("no upload");
  const [mine] = candidates(uploaded);
  expect(uploaded.origin).toBe("upload");
  expect([mine?.w, mine?.h]).toEqual([1080, 1920]);

  // 确认这个镜头 locks it; 分镜确认 again (取消确认 reopened it), and the next take starts from it.
  await page.getByRole("button", { name: "确认这个镜头" }).click();
  await expect(page.getByRole("button", { name: "取消确认" })).toBeVisible();
  await confirmBoard(page);
  const shot = await shotOf(request, "1-04");
  expect(shot.keyframe_sha256).toBe(mine?.sha256);
  const job = await send<Job>(request, `/products/${shot.video_product_id}/run`, {
    mode: "run",
    count: 1,
  });
  await finish(request, job);
  const video = await get<Product>(request, `/products/${shot.video_product_id}`);
  const take = video.versions.find((v) => v.job_id === job.id);
  expect(take?.params.request?.first_frame).toBe(mine?.sha256);
  note(missing);
  expect(errors).toEqual([]);
});

test("one first frame redrawn, inpainted and upscaled; the original still there", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const { errors, missing } = trackContract(page);
  const { request } = page;
  // The locked picture: the version and the candidate the shot starts from.
  const locked = (await shotOf(request, "1-05")).keyframe_sha256;
  const original = (await keyframeOf(request, "1-05")).versions.find((v) =>
    candidates(v).some((f) => f.sha256 === locked),
  );
  if (!original) throw new Error("1-05 has no locked first frame");
  await unconfirm(request, "1-05");
  await setUi(page, {});
  await openPage(page, "/s/demo/e/1/storyboard?shot=demo-shot-1-05");
  await expect(page.getByRole("heading", { name: "镜头 1-05" })).toBeVisible();
  const frames = page.getByRole("radiogroup", { name: "首帧" });
  const first = frames.getByRole("radio", { checked: true });
  const name = (await first.getAttribute("aria-label")) ?? "";
  expect(name).toMatch(/^v\d+ · A$/);
  const n = name.split(" ")[0] ?? ""; // "v2"
  // A new candidate is a new version, made current and picked; wait for it to land.
  const made = async (origin: string) => {
    await expect
      .poll(
        async () => (await keyframeOf(request, "1-05")).versions.some((v) => v.origin === origin),
        { timeout: 30_000 },
      )
      .toBe(true);
    await expect(frames.getByRole("radio", { checked: true })).toContainText(
      origin === "redraw" ? "以这张为底重画" : origin === "inpaint" ? "局部修复" : "放大",
    );
  };
  // The original is in 历史: 设为当前 brings it back to 首帧, to pick.
  const backToOriginal = async () => {
    await page.getByRole("tab", { name: /^历史 \d+$/ }).click();
    const history = page.getByRole("list", { name: /^历史 \d+$/ });
    await history
      .getByRole("listitem")
      .filter({ has: page.getByText(n, { exact: true }) })
      .getByRole("button", { name: "设为当前" })
      .click();
    const radio = frames.getByRole("radio", { name, exact: true });
    await radio.click();
    await expect(radio).toHaveAttribute("aria-checked", "true");
  };

  // 以这张为底重画: what to change, at the route's own (local) model.
  let dialog = page.getByRole("dialog", { name: `以这张为底重画 · 1-05 ${name}` });
  await (await openSource(page)).getByRole("menuitem", { name: /以这张为底重画…/ }).click();
  await dialog.getByLabel("想改什么").fill("窗外的雨再大一点");
  await dialog.getByRole("button", { name: "重画" }).click();
  await expect(page.getByText(`已开始重画 1-05 ${name}：出一张新候选。`)).toBeVisible();
  await made("redraw");

  // 局部修复 from the original again: a stroke painted on it, what goes there.
  await backToOriginal();
  await (await openSource(page)).getByRole("menuitem", { name: /局部修复…/ }).click();
  dialog = page.getByRole("dialog", { name: `局部修复 · 1-05 ${name}` });
  const submit = dialog.getByRole("button", { name: "修复" });
  await expect(submit).toBeDisabled();
  const canvas = dialog.getByLabel("在图上涂出要改的地方");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("no canvas");
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.4);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5, { steps: 8 });
  await page.mouse.up();
  await dialog.getByLabel("涂出来的地方画成").fill("桌上多一只空杯子");
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.getByText(`已开始局部修复 1-05 ${name}：出一张新候选。`)).toBeVisible();
  await made("inpaint");

  // 放大 the original to the delivery size.
  await backToOriginal();
  await (await openSource(page)).getByRole("menuitem", { name: /放大到 1080×1920/ }).click();
  await expect(
    page.getByText(`已开始放大 1-05 ${name} 到 1080×1920：出一张新候选。`),
  ).toBeVisible();
  await made("upscale");

  // Each is a candidate made from the original; the original is still there and locks again.
  const versions = (await keyframeOf(request, "1-05")).versions;
  for (const origin of ["redraw", "inpaint", "upscale"]) {
    const made = versions.filter((v) => v.origin === origin);
    expect(made, origin).toHaveLength(1);
    expect(made[0]?.parent_version_id, origin).toBe(original.id);
  }
  const upscaled = versions.find((v) => v.origin === "upscale");
  expect(upscaled ? candidates(upscaled).map((f) => [f.w, f.h]) : []).toEqual([[1080, 1920]]);
  await backToOriginal();
  await page.getByRole("button", { name: "确认这个镜头" }).click();
  await expect(page.getByRole("button", { name: "取消确认" })).toBeVisible();
  await confirmBoard(page);
  expect((await shotOf(request, "1-05")).keyframe_sha256).toBe(locked);
  note(missing);
  expect(errors).toEqual([]);
});
