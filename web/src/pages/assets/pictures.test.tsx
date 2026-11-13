import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { demoTiming } from "@/mocks/events";
import AssetsPage from "@/pages/Assets";
import { backend } from "@/test/backend";
import { fakeAssets } from "@/test/fakes/assets";
import { fakePictures } from "@/test/fakes/pictures";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

/** 图片来源与编辑 on the assets page (M5.5 step 16c, 草图 A3, A4). */

function Page() {
  useEventStream();
  return (
    <>
      <AssetsPage />
      <Toaster />
    </>
  );
}

const renderAssets = () =>
  renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/assets" element={<Page />} />
    </Routes>,
    "/s/demo/e/1/assets",
  );

const list = () => screen.getByRole("region", { name: "素材清单" });
const item = (name: RegExp) => within(list()).getByRole("button", { name });
const ready = () => screen.findByText("已锁定 7 / 9");
const productOf = (id: string) => fakeAssets.products.find((p) => p.id === `demo-p-asset-${id}`);
const moreOf = (id: string) =>
  fakePictures.products.find((p) => p.slot === "ref_more" && p.owner_id === id);
function views() {
  const p = fakeAssets.views[0];
  if (!p) throw new Error("林晚 has no views in the fixture");
  return p;
}
const viewFiles = () =>
  views()
    .versions.at(-1)
    ?.files.map((f) => f.sha256) ?? [];

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  demoTiming.runMs = 20;
});
afterEach(() => {
  vi.unstubAllGlobals();
  demoTiming.runMs = 1400;
});

describe("素材 · 换来源", () => {
  it("以这张为底重画 the picked candidate; 上传 is in the same menu", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/林晚出租屋/));
    const draft = productOf("room")?.versions.at(-1);
    await user.click(await screen.findByRole("button", { name: "换来源" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: /上传图片…/ })).toHaveTextContent("不裁切");
    expect(within(menu).getByRole("menuitem", { name: /放大到/ })).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: /以这张为底重画…/ }));
    const dialog = await screen.findByRole("dialog", { name: /以这张为底重画 · .* v1 · A/ });
    await user.click(within(dialog).getByRole("button", { name: "重画" }));
    await waitFor(() =>
      expect(fakeAssets.edits).toEqual([{ op: "redraw", version: draft?.id, idx: 0 }]),
    );
    expect(productOf("room")?.versions.at(-1)?.origin).toBe("redraw");
  });

  it("a locked reference takes no 换来源; on-screen text has no 更多参考图", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/红色长柄伞/));
    expect(screen.getByRole("button", { name: "换来源" })).toBeDisabled();
    expect(screen.getByRole("group", { name: "更多参考图" })).toBeInTheDocument();
    await user.click(within(list()).getByRole("radio", { name: "画面文字" }));
    await user.click(within(list()).getByRole("button", { pressed: false }));
    await screen.findByRole("heading", { level: 2, name: /手机/ });
    expect(screen.queryByRole("group", { name: "更多参考图" })).not.toBeInTheDocument();
  });
});

describe("素材 · 更多参考图", () => {
  it("adds a picture for the outfit while locked, then removes it", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    const set = await screen.findByRole("group", { name: "更多参考图" });
    expect(within(set).getByText("0 / 8 张")).toBeInTheDocument();
    await user.selectOptions(within(set).getByRole("combobox", { name: "参考什么" }), "服装");
    await user.upload(
      within(set).getByLabelText("选一张图片加进更多参考图"),
      new File(["png"], "外套.png", { type: "image/png" }),
    );
    const pic = await within(set).findByRole("img", { name: "更多参考图 1（服装）" });
    expect(pic).toBeInTheDocument();
    expect(
      moreOf("linwan")
        ?.versions.at(-1)
        ?.files.map((f) => f.purpose),
    ).toEqual(["outfit"]);
    await user.click(within(set).getByRole("button", { name: "删掉 更多参考图 1（服装）" }));
    await waitFor(() => expect(moreOf("linwan")?.versions.at(-1)?.files).toEqual([]));
    expect(within(set).queryByRole("img")).not.toBeInTheDocument();
  });
});

describe("素材 · 补视图换一张", () => {
  it("重画这张 draws one view again; the set is busy while it runs", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    const region = await screen.findByRole("region", { name: "补视图" });
    await within(region).findByRole("img", { name: "背面" });
    await user.click(within(region).getByRole("button", { name: "重画背面" }));
    await waitFor(() => expect(fakeAssets.views_replaced).toEqual([{ view: "back", file: null }]));
    expect(await screen.findByText("正在重画背面，其余 5 张不变。")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(region).getByRole("button", { name: "重画侧面" })).toBeDisabled(),
    );
  });

  it("上传 replaces one view, the other five kept", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    const region = await screen.findByRole("region", { name: "补视图" });
    await within(region).findByRole("img", { name: "侧面" });
    const before = viewFiles();
    await user.click(within(region).getByRole("button", { name: "上传一张换掉侧面" }));
    await user.upload(
      screen.getByLabelText("选择要换上的图片"),
      new File(["png"], "侧面.png", { type: "image/png" }),
    );
    await waitFor(() =>
      expect(fakeAssets.views_replaced).toEqual([{ view: "side", file: "侧面.png" }]),
    );
    const after = viewFiles();
    expect(after[0]).not.toBe(before[0]);
    expect(after.slice(1)).toEqual(before.slice(1));
    expect(
      await screen.findByText("已换上侧面，其余 5 张不变；历史里能换回。"),
    ).toBeInTheDocument();
  });

  it("an outdated set is redrawn whole: 重画这张 is greyed, 上传 still works", async () => {
    views().status = "stale";
    renderAssets();
    await ready();
    const region = await screen.findByRole("region", { name: "补视图" });
    await within(region).findByRole("img", { name: "背面" });
    expect(within(region).getByRole("button", { name: "重画背面" })).toBeDisabled();
    expect(within(region).getByRole("button", { name: "上传一张换掉背面" })).toBeEnabled();
  });
});

describe("素材 · 新建素材", () => {
  it("a prop with its size, drawn from the description; the list marks it 手动", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(within(list()).getByRole("button", { name: "新建素材" }));
    const dialog = await screen.findByRole("dialog", { name: "新建素材" });
    expect(within(dialog).getByRole("radio", { name: "道具" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    const create = within(dialog).getByRole("button", { name: "新建" });
    expect(create).toBeDisabled();
    await user.type(within(dialog).getByLabelText("名字"), "旧钥匙扣");
    await user.type(within(dialog).getByLabelText("描述"), "黄铜钥匙扣，挂着小铃铛。");
    await user.type(within(dialog).getByLabelText("真实尺寸"), "约 5 cm");
    await user.click(create);

    await waitFor(() =>
      expect(fakeAssets.created).toEqual([
        { kind: "prop", name: "旧钥匙扣", description: "黄铜钥匙扣，挂着小铃铛。" },
      ]),
    );
    const made = fakeAssets.assets.find((a) => a.name === "旧钥匙扣");
    expect(made?.physical?.size).toBe("约 5 cm");
    await waitFor(() =>
      expect(fakeAssets.products.find((p) => p.id === made?.product_id)?.versions).toHaveLength(1),
    );
    expect(await screen.findByText("已新建「旧钥匙扣」，正在按描述生成候选。")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "旧钥匙扣" })).toBeInTheDocument();
    const row = item(/旧钥匙扣/);
    expect(row).toHaveTextContent("手动");
    expect(row).toHaveTextContent("还没有镜头用");
    expect(screen.getByText("来源：手动新建")).toBeInTheDocument();
  });

  it("with an uploaded picture; the same kind and name is refused", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(within(list()).getByRole("button", { name: "新建素材" }));
    let dialog = await screen.findByRole("dialog", { name: "新建素材" });
    await user.click(within(dialog).getByRole("radio", { name: "场景" }));
    expect(within(dialog).queryByLabelText("真实尺寸")).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("名字"), "天台");
    await user.click(within(dialog).getByRole("radio", { name: "上传图片" }));
    expect(within(dialog).getByRole("button", { name: "新建" })).toBeDisabled();
    await user.upload(
      within(dialog).getByLabelText("选择要上传的图片"),
      new File(["png"], "天台.png", { type: "image/png" }),
    );
    expect(dialog).toHaveTextContent("天台.png");
    await user.click(within(dialog).getByRole("button", { name: "新建" }));
    await waitFor(() => expect(fakeAssets.uploads).toEqual([{ id: "manual-1", name: "天台.png" }]));
    expect(await screen.findByRole("heading", { level: 2, name: "天台" })).toBeInTheDocument();

    await user.click(within(list()).getByRole("button", { name: "新建素材" }));
    dialog = await screen.findByRole("dialog", { name: "新建素材" });
    await user.click(within(dialog).getByRole("radio", { name: "场景" }));
    await user.type(within(dialog).getByLabelText("名字"), "天台");
    await user.click(within(dialog).getByRole("button", { name: "新建" }));
    expect(await screen.findByText("已经有叫「天台」的同类素材")).toBeInTheDocument();
    expect(fakeAssets.created).toHaveLength(1);
    // Still open with what was typed: change the name and try again.
    expect(screen.getByRole("dialog", { name: "新建素材" })).toBeInTheDocument();
  });
});
