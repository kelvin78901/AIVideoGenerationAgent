import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import AssetsPage from "@/pages/Assets";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

// Content typed by the user.
const NEW_DESC = "27 岁，短发。";

function Page() {
  useEventStream();
  return <AssetsPage />;
}

function renderAssets() {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/assets" element={<Page />} />
    </Routes>,
    "/s/demo/e/1/assets",
  );
}

const list = () => screen.getByRole("region", { name: "素材清单" });
const item = (name: RegExp) => within(list()).getByRole("button", { name });
const asset = (id: string) => getDb().assets.find((a) => a.id === id);
const productOf = (id: string) => getDb().products[`demo-p-asset-${id}`];
const ready = () => screen.findByText("已锁定 7 / 13");

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  demoTiming.runMs = 20;
});
afterEach(() => {
  vi.unstubAllGlobals();
  demoTiming.runMs = 1400;
});

describe("AssetsPage", () => {
  it("lists 13 assets, 7 locked, with the analysis summary", async () => {
    renderAssets();
    await ready();
    expect(
      screen.getByText("从剧本分析出：角色 2 · 场景 3 · 道具 4 · 画面文字 2 · 音色 2"),
    ).toBeInTheDocument();
    expect(within(list()).getAllByRole("button", { pressed: false })).toHaveLength(12);
    expect(screen.getByText("当前产物 · 林晚 · 参考图 4 张候选")).toBeInTheDocument();
    expect(screen.getByText(/v2 · Nano Banana Pro/)).toHaveTextContent("已锁定");
    expect(screen.getByRole("link", { name: "1-09" })).toBeInTheDocument();
  });

  it("filters by kind", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(within(list()).getByRole("radio", { name: "画面文字" }));
    expect(within(list()).getAllByRole("button")).toHaveLength(2);
  });

  it("checks on-screen text candidates with OCR; compositing in post makes them all match", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/便利贴手写/));
    const cands = screen.getByRole("radiogroup", { name: "候选" });
    expect(within(cands).getByRole("radio", { name: "v1 · B" })).toHaveTextContent(
      "OCR 不一致：有错字",
    );
    expect(within(cands).getByRole("radio", { name: "v1 · D" })).toHaveTextContent(
      "OCR 不一致：缺字或缺标点",
    );
    await user.click(screen.getByRole("radio", { name: "后期贴字（推荐）" }));
    await waitFor(() => expect(within(cands).getAllByText("OCR 一致")).toHaveLength(4));
    expect(asset("txt1")?.text?.method).toBe("composite");
  });

  it("picks a candidate and locks it; the count goes to 8 / 13", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/旧黑发圈/));
    await user.click(screen.getByRole("radio", { name: "v1 · C" }));
    await waitFor(() => expect(asset("band")?.pick).toBe(2));
    await user.click(screen.getByRole("button", { name: "锁定为参考" }));
    expect(await screen.findByText("已锁定 8 / 13")).toBeInTheDocument();
    expect(item(/旧黑发圈/)).toHaveTextContent("已锁定");
    expect(productOf("band")?.locked_hash).not.toBeNull();
    expect(screen.getByRole("radio", { name: "v1 · C" })).toBeDisabled();
  });

  it("unlocking previews the affected shots in a dialog; 只改这里 unlocks", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/红色长柄伞/));
    await user.click(screen.getByRole("button", { name: "解锁" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("解锁「红色长柄伞」会影响用到它的镜头");
    expect(dialog).toHaveTextContent("分镜 · 1-02 1-08 1-09，共 3 个镜头用它做参考");
    await user.click(within(dialog).getByRole("button", { name: "只改这里，下游标待更新" }));
    expect(await screen.findByText("已锁定 6 / 13")).toBeInTheDocument();
    expect(item(/红色长柄伞/)).toHaveTextContent("待选");
    expect(getDb().progress[EP1]?.steps.storyboard.stale).toBe(3);
  });

  it("「撤销」 keeps the asset locked", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/红色长柄伞/));
    await user.click(screen.getByRole("button", { name: "解锁" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(productOf("umbrella")?.locked_hash).not.toBeNull();
  });

  it("generates candidates for an asset that has none", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/楼下便利店/));
    expect(screen.getByText("还没生成。点上方或右侧的「重跑」出 4 张候选。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "锁定为参考" })).toBeDisabled();
    await user.click(screen.getAllByRole("button", { name: /^重跑/ })[0] as HTMLElement);
    const cands = await screen.findByRole("radiogroup", { name: "候选" });
    expect(within(cands).getAllByRole("radio")).toHaveLength(4);
    await waitFor(() => expect(item(/楼下便利店/)).toHaveTextContent("待选"));
  });

  it("voices: three candidates to audition, script lines to try", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/^林晚\s*音色/));
    expect(screen.getByText("当前产物 · 林晚 · 音色候选 3 个")).toBeInTheDocument();
    const voices = screen.getByRole("radiogroup", { name: "音色候选" });
    expect(within(voices).getAllByRole("radio")).toHaveLength(3);
    const play = screen.getByRole("button", { name: "试听 B" });
    await user.click(play);
    expect(screen.getByRole("button", { name: "暂停 B" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "试读：……周屿？" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "文字描述设计" })).toBeChecked();
  });

  it("an Inspector chip of another kind shows the first asset of that kind", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(screen.getByRole("button", { name: "画面文字" }));
    expect(
      await screen.findByText("当前产物 · 便利贴手写 · 文字素材 4 张候选"),
    ).toBeInTheDocument();
  });

  it("saves the description as the intent of the next run", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    const desc = screen.getByLabelText("描述（就是这条素材的提示词意图层）");
    await user.clear(desc);
    await user.type(desc, NEW_DESC);
    await user.tab();
    await waitFor(() => expect(asset("linwan")?.intent).toBe(NEW_DESC));
    expect(productOf("linwan")?.prompt?.intent).toBe(NEW_DESC);
  });
});
