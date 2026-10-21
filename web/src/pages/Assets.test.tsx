import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import AssetsPage from "@/pages/Assets";
import { backend } from "@/test/backend";
import { fakeAssets } from "@/test/fakes/assets";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

// Content typed by the user.
const NEW_DESC = "十来平米，只开一盏台灯。";

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
const asset = (id: string) => fakeAssets.assets.find((a) => a.id === id);
const productOf = (id: string) => fakeAssets.products.find((p) => p.id === `demo-p-asset-${id}`);
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
    expect(await screen.findByText("当前产物 · 林晚 · 参考图 4 张候选")).toBeInTheDocument();
    // The API final v2 stays on screen; the picture locked from it is a version of its own.
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

  it("shows each text candidate's OCR check; compositing in post takes a rerun", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/便利贴手写/));
    const cands = screen.getByRole("radiogroup", { name: "候选" });
    const cand = (name: string) => within(cands).getByRole("radio", { name });
    expect(within(cand("v1 · A")).getByRole("img", { name: "v1 · A" })).toBeInTheDocument();
    expect(cand("v1 · A")).toHaveTextContent("模型直接出字OCR 一致");
    expect(cand("v1 · B")).toHaveTextContent("OCR 不一致：有错字");
    expect(cand("v1 · D")).toHaveTextContent("OCR 不一致：缺字或缺标点");
    // The candidates were drawn by the model: switching the method changes nothing until a rerun.
    await user.click(screen.getByRole("radio", { name: "后期贴字（推荐）" }));
    await waitFor(() => expect(asset("txt1")?.text?.method).toBe("composite"));
    expect(
      await screen.findByText(
        "这一版是按「模型直接出字」出的「楼下便利店，等你到十二点。」；字或做法改了，点「重跑」按现在的设置出",
      ),
    ).toBeInTheDocument();
    expect(cand("v1 · B")).toHaveTextContent("OCR 不一致：有错字");
    await user.click(screen.getAllByRole("button", { name: /^重跑/ })[0] as HTMLElement);
    const base = await screen.findByRole("radio", { name: "v2 · A" });
    // A blank base, the text laid over it as post will paste it.
    expect(base).toHaveTextContent("楼下便利店，等你到十二点。");
    expect(base).toHaveTextContent("无字底图 + 后期贴字OCR 确认底图没有字");
    expect(
      screen.getByText("每张都做了 OCR，确认底图上没有字；上面叠的字是后期贴字的预览"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/这一版是按/)).not.toBeInTheDocument();
  });

  it("locking text OCR read differently asks first; 「仍然锁定」 locks it", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/便利贴手写/));
    await user.click(screen.getByRole("radio", { name: "v1 · B" }));
    await waitFor(() => expect(asset("txt1")?.pick).toBe(1));
    await user.click(screen.getByRole("button", { name: "锁定为参考" }));
    let dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("候选 B 的字和要求不一致");
    expect(dialog).toHaveTextContent("OCR 读出来是「楼下便利店，等你到十二占。」");
    expect(dialog).toHaveTextContent("要求是「楼下便利店，等你到十二点。」");
    await user.click(within(dialog).getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(productOf("txt1")?.locked_hash).toBeNull();

    await user.click(screen.getByRole("button", { name: "锁定为参考" }));
    dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "仍然锁定" }));
    expect(await screen.findByText("已锁定 8 / 13")).toBeInTheDocument();
    expect(productOf("txt1")?.locked_hash).not.toBeNull();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
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

  it("unlocking a character lists the views drawn from it, then its shots", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(screen.getByRole("button", { name: "解锁" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(
      "补视图 · 「林晚」的侧面、背面和表情按这张参考图画，锁定新的一张后会重画",
    );
    expect(dialog).toHaveTextContent("分镜 · 1-01 1-04 1-05 1-06 1-08 1-09，共 6 个镜头用它做参考");
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
    await user.click(item(/林晚出租屋/));
    const desc = screen.getByLabelText("描述（就是这条素材的提示词意图层）");
    await user.clear(desc);
    await user.type(desc, NEW_DESC);
    await user.tab();
    await waitFor(() => expect(asset("room")?.intent).toBe(NEW_DESC));
    expect(productOf("room")?.prompt?.intent).toBe(NEW_DESC);
  });

  it("shows each candidate's picture; 「用 API 出终版」 makes one picture from the picked draft", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/林晚出租屋/));
    const cands = screen.getByRole("radiogroup", { name: "候选" });
    const pictures = within(cands).getAllByRole("img");
    expect(pictures).toHaveLength(4);
    const draft = productOf("room")?.versions.at(-1);
    const sha = draft?.files.find((f) => f.idx === 2)?.sha256 ?? "";
    expect(within(cands).getByRole("img", { name: "v1 · C" })).toHaveAttribute(
      "src",
      `/api/v1/files/${sha}`,
    );
    await user.click(within(cands).getByRole("radio", { name: "v1 · C" }));
    await waitFor(() => expect(asset("room")?.pick).toBe(2));
    await user.click(screen.getByRole("button", { name: "用 API 出终版 · 约 $0.14" }));
    await waitFor(() => expect(productOf("room")?.versions).toHaveLength(2));
    const final = productOf("room")?.versions.at(-1);
    expect(final).toMatchObject({ stage: "final", parent_version_id: draft?.id });
    expect(final?.model_key).toBe("google/nano-banana-pro");
    const now = await screen.findByRole("radio", { name: "v2 · A" });
    expect(within(now).getByRole("img")).toBeInTheDocument();
    // The final is not a draft: no second final from it.
    expect(screen.queryByRole("button", { name: /用 API 出终版/ })).not.toBeInTheDocument();
  });

  it("uploads a reference picture as a picked candidate", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/旧黑发圈/));
    const file = new File(["png"], "发圈.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("选择要上传的图片"), file);
    await waitFor(() => expect(fakeAssets.uploads).toEqual([{ id: "band", name: "发圈.png" }]));
    expect(productOf("band")?.versions.at(-1)?.origin).toBe("upload");
    expect(await screen.findByRole("radio", { name: "v2 · A" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    // A locked asset takes no upload.
    await user.click(item(/红色长柄伞/));
    expect(screen.getByRole("button", { name: "上传参考图" })).toBeDisabled();
  });

  it("a locked character shows the views drawn from it", async () => {
    renderAssets();
    await ready();
    const views = await screen.findByRole("region", { name: "补视图" });
    for (const name of ["侧面", "背面", "表情"])
      expect(await within(views).findByRole("img", { name })).toBeInTheDocument();
  });

  it("「出现在」 lists the scenes, linked to the script", async () => {
    renderAssets();
    await ready();
    const linwan = asset("linwan");
    const first = linwan?.scenes[0];
    const link = screen.getByRole("link", { name: "场 1" });
    expect(link).toHaveAttribute(
      "href",
      `/s/demo/e/1/script?line=${first?.line_ids[0] ?? first?.scene_id ?? ""}`,
    );
    expect(screen.getByRole("link", { name: "场 2" })).toBeInTheDocument();
    expect(item(/^林晚\s*角色/)).toHaveTextContent("2 场 · 6 个镜头");
  });

  it("the matrix: one row per scene, a cell links to the line; a column picks the asset", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(screen.getByRole("radio", { name: "出场矩阵" }));
    const table = await screen.findByRole("table", { name: "出场矩阵" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3); // the header and two scenes
    const cell = within(table).getByRole("link", { name: /^角色「林晚」在场 1：/ });
    expect(cell.getAttribute("href")).toMatch(/^\/s\/demo\/e\/1\/script\?line=/);
    expect(
      within(table).getByRole("link", { name: "场景「老小区楼道 · 夜」在场 1（整场）" }),
    ).toHaveTextContent("整场");
    await user.click(within(table).getByRole("button", { name: /红色长柄伞/ }));
    expect(await screen.findByText("当前产物 · 红色长柄伞 · 参考图 4 张候选")).toBeInTheDocument();
  });

  it("「重新分析剧本」 starts the analysis job", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(screen.getByRole("button", { name: "重新分析剧本" }));
    await waitFor(() => expect(fakeAssets.analyses).toEqual(["demo-e1"]));
  });
});
