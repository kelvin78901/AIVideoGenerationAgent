import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import StoryboardPage from "@/pages/Storyboard";
import { backend } from "@/test/backend";
import { fakeConfig } from "@/test/fakes/config";
import { fakeShots } from "@/test/fakes/shots";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

/** 图片来源与编辑 on the storyboard's 首帧 (M5.5 step 16a, 草图 S3, S5–S7). */

function Page() {
  useEventStream();
  return (
    <>
      <StoryboardPage />
      <Toaster />
    </>
  );
}

const renderBoard = () =>
  renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/storyboard" element={<Page />} />
    </Routes>,
    "/s/demo/e/1/storyboard",
  );

const shot = (label: string) => fakeShots.shots.find((s) => s.label === label);
const keyframe = (label: string) =>
  fakeShots.keyframes.find((p) => p.id === shot(label)?.keyframe_product_id);

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("radiogroup", { name: "首帧" });
  await user.click(screen.getByRole("button", { name: "换来源" }));
  return screen.findByRole("menu");
}

/** jsdom decodes no pictures: say the one on screen is `w × h`. */
function decoded(img: HTMLElement, w: number, h: number) {
  Object.defineProperty(img, "naturalWidth", { value: w });
  Object.defineProperty(img, "naturalHeight", { value: h });
  fireEvent.load(img);
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  URL.createObjectURL = () => "blob:picture";
  URL.revokeObjectURL = () => undefined;
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("首帧 · 换来源", () => {
  it("uploads a picture cut to 9:16: the box at the left, a new picked candidate", async () => {
    const user = userEvent.setup();
    renderBoard();
    const menu = await openMenu(user);
    expect(within(menu).getByRole("menuitem", { name: /重新生成一组/ })).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: /上传图片…/ }));
    const file = new File(["jpeg"], "IMG_2231.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByTestId("keyframe-upload"), file);
    const dialog = await screen.findByRole("dialog", { name: "上传首帧 · 镜头 1-04" });
    decoded(within(dialog).getByRole("img", { name: "IMG_2231.jpg" }), 4032, 3024);
    expect(dialog).toHaveTextContent("原图 4032×3024");
    expect(dialog).toHaveTextContent("成片 9:16 → 裁出 1701×3024 → 缩到 1080×1920");
    await user.click(within(dialog).getByRole("radio", { name: "靠左" }));
    expect(within(dialog).queryByRole("status")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "上传为候选" }));

    await waitFor(() => expect(fakeShots.edits).toHaveLength(1));
    expect(fakeShots.edits[0]).toEqual({
      kind: "upload",
      shot: shot("1-04")?.id,
      name: "IMG_2231.jpg",
      box: { x: 0, y: 0, w: 1701, h: 3024 },
    });
    expect(await screen.findByText("已上传为镜头 1-04 的新候选，并选中了它。")).toBeInTheDocument();
    expect(await screen.findByRole("radio", { name: "v2 · A" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByText("上传 · IMG_2231.jpg")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a small picture is only a warning; arrow keys move the box", async () => {
    const user = userEvent.setup();
    renderBoard();
    await user.click(within(await openMenu(user)).getByRole("menuitem", { name: /上传图片…/ }));
    await user.upload(
      screen.getByTestId("keyframe-upload"),
      new File(["png"], "small.png", { type: "image/png" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "上传首帧 · 镜头 1-04" });
    decoded(within(dialog).getByRole("img", { name: "small.png" }), 1280, 1138);
    expect(within(dialog).getByRole("status")).toHaveTextContent(
      "裁出来 640×1138，小于草稿尺寸 768×1366，放大后会发糊。",
    );
    const box = within(dialog).getByRole("slider", { name: "裁切框" });
    fireEvent.keyDown(box, { key: "ArrowRight" });
    await user.click(within(dialog).getByRole("button", { name: "上传为候选" }));
    await waitFor(() => expect(fakeShots.edits).toHaveLength(1));
    // Centred at 320, then 2 % of 1280 (25.6 px) to the right.
    expect(fakeShots.edits[0]).toMatchObject({ box: { x: 346, y: 0, w: 640, h: 1138 } });
    expect(await screen.findByText("分辨率偏低")).toBeInTheDocument();
  });

  it("以这张为底重画: what to change and how much, on the picked candidate", async () => {
    const user = userEvent.setup();
    renderBoard();
    await user.click(await screen.findByRole("radio", { name: "v1 · B" }));
    await waitFor(() => expect(shot("1-04")?.keyframe_pick).toBe(1));
    const draft = keyframe("1-04")?.versions.at(-1);
    await user.click(
      within(await openMenu(user)).getByRole("menuitem", { name: /以这张为底重画…/ }),
    );
    const dialog = await screen.findByRole("dialog", { name: "以这张为底重画 · 1-04 v1 · B" });
    await user.type(within(dialog).getByLabelText("想改什么"), "门再旧一点");
    // The route's own mode first (local under 均衡), its API model one click away.
    expect(within(dialog).getByRole("radio", { name: /Klein.* · 免费/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(within(dialog).getByRole("radio", { name: "Nano Banana 2.1 · $0.05 / 张" }));
    expect(within(dialog).getByText("API 模型没有数值强度，幅度写进提示词。")).toBeInTheDocument();
    fireEvent.keyDown(within(dialog).getByRole("slider", { name: "改动幅度" }), {
      key: "ArrowRight",
    });
    await user.click(within(dialog).getByRole("button", { name: "重画" }));

    await waitFor(() => expect(fakeShots.edits).toHaveLength(1));
    expect(fakeShots.edits[0]).toEqual({
      kind: "redraw",
      version: draft?.id,
      body: { idx: 1, prompt: "门再旧一点", strength: 0.55, where: "api" },
    });
    expect(await screen.findByText("已开始重画 1-04 v1 · B：出一张新候选。")).toBeInTheDocument();
    expect(await screen.findByText("以这张为底重画")).toBeInTheDocument();
    expect(keyframe("1-04")?.versions.at(-1)).toMatchObject({
      origin: "redraw",
      parent_version_id: draft?.id,
    });
  });

  it("局部修复: paint the mask, say what goes there; nothing painted, nothing to send", async () => {
    const user = userEvent.setup();
    // jsdom has no canvas: a context that draws nothing and a mask of a few bytes.
    const ctx = new Proxy({} as Record<string, unknown>, {
      get: (_, key) => (key === "getImageData" ? () => ({}) : () => undefined),
      set: () => true,
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      ctx as unknown as CanvasRenderingContext2D,
    );
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((cb) =>
      // Node's File (test/setup.ts): the one Node's FormData takes.
      cb(new File(["mask"], "mask.png", { type: "image/png" })),
    );
    renderBoard();
    const draft = keyframe("1-04")?.versions.at(-1);
    await user.click(within(await openMenu(user)).getByRole("menuitem", { name: /局部修复…/ }));
    const dialog = await screen.findByRole("dialog", { name: "局部修复 · 1-04 v1 · A" });
    const submit = within(dialog).getByRole("button", { name: "修复" });
    expect(submit).toBeDisabled();
    expect(dialog).toHaveTextContent("先在图上涂出要改的地方");
    fireEvent.pointerDown(within(dialog).getByLabelText("在图上涂出要改的地方"));
    expect(submit).toBeEnabled();
    await user.type(within(dialog).getByLabelText("涂出来的地方画成"), "伞柄上贴一张便利贴");
    await user.click(submit);

    await waitFor(() => expect(fakeShots.edits).toHaveLength(1));
    expect(fakeShots.edits[0]).toEqual({
      kind: "inpaint",
      version: draft?.id,
      idx: 0,
      prompt: "伞柄上贴一张便利贴",
      where: "local",
      mask: 4,
    });
    expect(
      await screen.findByText("已开始局部修复 1-04 v1 · A：出一张新候选。"),
    ).toBeInTheDocument();
  });

  it("放大 to the delivery size; greyed with the reason when this machine cannot", async () => {
    const user = userEvent.setup();
    renderBoard();
    const draft = keyframe("1-04")?.versions.at(-1);
    await user.click(
      within(await openMenu(user)).getByRole("menuitem", { name: /放大到 1080×1920/ }),
    );
    await waitFor(() => expect(fakeShots.edits).toHaveLength(1));
    expect(fakeShots.edits[0]).toEqual({ kind: "upscale", version: draft?.id, idx: 0 });
    expect(
      await screen.findByText("已开始放大 1-04 v1 · A 到 1080×1920：出一张新候选。"),
    ).toBeInTheDocument();
    // The upscaled one is the delivery size: nothing more to upscale.
    await user.click(screen.getByRole("button", { name: "换来源" }));
    expect(await screen.findByRole("menuitem", { name: /已经是这个尺寸了/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("放大 is greyed when the upscaler is not installed", async () => {
    const iup = fakeConfig.catalog.components.find((c) => c.id === "iup");
    if (iup) iup.unavailable = { local: { code: "machine_missing", params: { count: 2 } } };
    const user = userEvent.setup();
    renderBoard();
    const item = within(await openMenu(user)).getByRole("menuitem", { name: /放大到 1080×1920/ });
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("这台机器还缺 2 项运行环境，去「环境与安装」补装");
  });

  it("a confirmed shot has no 换来源", async () => {
    const s = shot("1-04");
    if (s) s.confirmed = true;
    const kf = keyframe("1-04");
    if (kf) kf.locked_hash = "sha256:x";
    renderBoard();
    await screen.findByRole("radiogroup", { name: "首帧" });
    expect(screen.queryByRole("button", { name: "换来源" })).not.toBeInTheDocument();
  });
});
