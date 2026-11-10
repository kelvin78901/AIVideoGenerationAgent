import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { demoTiming } from "@/mocks/events";
import AssetsPage from "@/pages/Assets";
import { backend } from "@/test/backend";
import { fakeAssets } from "@/test/fakes/assets";
import { fakeDub } from "@/test/fakes/dub";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

// Content typed by the user.
const NEW_DESC = "十来平米，只开一盏台灯。";
const NEW_LOOK = "二十六岁，齐耳短发。";

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
const ready = () => screen.findByText("已锁定 7 / 9");

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
  it("lists 12 assets, 7 locked, with the analysis summary", async () => {
    renderAssets();
    await ready();
    expect(
      screen.getByText("从剧本分析出：角色 2 · 场景 3 · 道具 4 · 画面文字 1 · 音色 2"),
    ).toBeInTheDocument();
    expect(within(list()).getAllByRole("button", { pressed: false })).toHaveLength(11);
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
    expect(within(list()).getAllByRole("button")).toHaveLength(1);
  });

  it("a prop's writing: each candidate shows its OCR check (M5.5: only a warning)", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/黄色便利贴/));
    const cands = screen.getByRole("radiogroup", { name: "候选" });
    const cand = (name: string) => within(cands).getByRole("radio", { name });
    expect(within(cand("v1 · A")).getByRole("img", { name: "v1 · A" })).toBeInTheDocument();
    expect(cand("v1 · A")).toHaveTextContent("OCR 一致");
    expect(cand("v1 · B")).toHaveTextContent("OCR 不一致：有错字");
    expect(cand("v1 · D")).toHaveTextContent("OCR 不一致：缺字或缺标点");
  });

  it("a locked prop's size and pen go through the impact; its writing has no method", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/黄色便利贴/));
    const keep = async () => {
      const dialog = await screen.findByRole("alertdialog");
      expect(dialog).toHaveTextContent("「黄色便利贴」已锁定，改动会影响下游");
      await user.click(within(dialog).getByRole("button", { name: "只改这里，下游标待更新" }));
    };
    const size = screen.getByLabelText("真实尺寸");
    await user.clear(size);
    await user.type(size, "7.5 cm 见方");
    await user.tab();
    await keep();
    await waitFor(() => expect(asset("note")?.physical?.size).toBe("7.5 cm 见方"));
    expect(asset("note")?.physical?.material).toBe("黄色便利贴纸");
    expect(screen.getByLabelText("道具上的字（逐字核对）")).toHaveValue(
      "楼下便利店，等你到十二点。",
    );
    expect(screen.queryByRole("radiogroup", { name: "做法" })).not.toBeInTheDocument();
    const styles = screen.getByRole("radiogroup", { name: "字体风格" });
    expect(within(styles).queryByRole("radio", { name: "屏幕界面" })).not.toBeInTheDocument();
    const pens = screen.getByRole("radiogroup", { name: "用什么写" });
    expect(within(pens).getByRole("radio", { name: "圆珠笔" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(within(pens).getByRole("radio", { name: "马克笔" }));
    await keep();
    await waitFor(() => expect(asset("note")?.text?.pen).toBe("marker"));
  });

  it("a prop shows its scale reference next to a character; 重画这张 redraws it", async () => {
    const views = fakeAssets.views[0];
    if (!views) throw new Error("no views product");
    const scale = structuredClone(views);
    Object.assign(scale, { id: "demo-p-scale-umbrella", owner_id: "umbrella", slot: "ref_scale" });
    const v = scale.versions.find((x) => x.id === scale.adopted_version_id);
    const file = v?.files[0];
    if (!v || !file) throw new Error("no adopted views picture");
    v.payload = { character: "林晚" };
    v.files = [{ ...file, role: "scale", idx: 0 }];
    fakeAssets.views.push(scale);
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/红色长柄伞/));
    const region = await screen.findByRole("region", { name: "比例参考" });
    expect(within(region).getByText("和林晚同框，看大小对不对")).toBeInTheDocument();
    expect(await within(region).findByRole("img", { name: "林晚和它同框" })).toBeInTheDocument();
    expect(screen.getByLabelText("真实尺寸")).toHaveValue(asset("umbrella")?.physical?.size);
  });

  it("picks a candidate and locks it; the count goes to 8 / 9", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/旧黑发圈/));
    await user.click(screen.getByRole("radio", { name: "v1 · C" }));
    await waitFor(() => expect(asset("band")?.pick).toBe(2));
    await user.click(screen.getByRole("button", { name: "锁定为参考" }));
    expect(await screen.findByText("已锁定 8 / 9")).toBeInTheDocument();
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
    expect(dialog).toHaveTextContent("分镜 · 1-02、1-06、1-09，共 3 个镜头用它做参考");
    expect(dialog).toHaveTextContent("其中镜头 1-02 已确认");
    await user.click(within(dialog).getByRole("button", { name: "只改这里，下游标待更新" }));
    expect(await screen.findByText("已锁定 6 / 9")).toBeInTheDocument();
    expect(item(/红色长柄伞/)).toHaveTextContent("待选");
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
    expect(dialog).toHaveTextContent(
      "分镜 · 1-01、1-04、1-05、1-06、1-08、1-09，共 6 个镜头用它做参考",
    );
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

  it("a locked voice shows its final: the sample, five emotions, lines to try", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/^林晚\s*音色/));
    expect(screen.getByText("当前产物 · 林晚 · 音色候选 3 个")).toBeInTheDocument();
    const final = await screen.findByRole("region", { name: "终版" });
    expect(final).toHaveTextContent("终版 · 偏低沉 · API 音色设计");
    expect(within(final).getByRole("button", { name: "播放：样音" })).toBeInTheDocument();
    const variants = within(final).getByRole("list", { name: "情绪变体" });
    expect(
      within(variants)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["平静", "愤怒", "哭腔", "耳语", "喊叫"].map((e) => expect.stringContaining(e)));
    expect(screen.getByRole("button", { name: "播放：……周屿？" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "文字描述设计" })).toBeChecked();
    // 声音克隆 comes later.
    expect(screen.getByRole("radio", { name: "声音克隆" })).toBeDisabled();
  });

  it("a voice: free auditions, then the final, which is what gets locked", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/^周屿\s*音色/));
    await user.click(screen.getAllByRole("button", { name: /^重跑/ })[0] as HTMLElement);
    const voices = await screen.findByRole("radiogroup", { name: "音色候选" });
    expect(within(voices).getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "播放：v1 · B · 更清亮" })).toBeInTheDocument();
    const lock = screen.getByRole("button", { name: "锁定为参考" });
    expect(lock).toBeDisabled();
    expect(lock).toHaveAttribute("title", "试听不能直接锁定：先出终版");
    await user.click(within(voices).getAllByRole("radio")[1] as HTMLElement);
    await waitFor(() => expect(asset("vzhouyu")?.pick).toBe(1));
    await user.click(screen.getByRole("button", { name: "用 MiniMax Speech 2.8 HD 出终版" }));
    expect(await screen.findByRole("region", { name: "终版" })).toBeInTheDocument();
    const final = productOf("vzhouyu")?.versions.at(-1);
    expect(final).toMatchObject({ stage: "final", model_key: "minimax/speech-2.8-hd" });
    await user.click(screen.getByRole("button", { name: "锁定为参考" }));
    await waitFor(() => expect(productOf("vzhouyu")?.adopted_version_id).toBe(final?.id));
    expect(item(/^周屿\s*音色/)).toHaveTextContent("已锁定");
  });

  it("an Inspector chip of another kind shows the first asset of that kind", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(screen.getByRole("button", { name: "画面文字" }));
    expect(
      await screen.findByText("当前产物 · 手机锁屏时间 · 文字素材 4 张候选"),
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

  it("a locked asset's new description shows the impact first; 只改这里 keeps the lock", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    const before = productOf("linwan")?.locked_hash;
    const desc = screen.getByLabelText("描述（就是这条素材的提示词意图层）");
    await user.clear(desc);
    await user.type(desc, NEW_LOOK);
    await user.tab();
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("「林晚」已锁定，改动会影响下游");
    expect(dialog).toHaveTextContent(`新描述：${NEW_LOOK}`);
    expect(dialog).toHaveTextContent("「林晚」按新的设置重新出候选；锁定的还是现在这个");
    expect(dialog).toHaveTextContent("补视图 · 「林晚」的侧面、背面和表情按这张参考图画");
    expect(dialog).toHaveTextContent("出现在场 1、2：剧本不用改");
    expect(dialog).toHaveTextContent("锁定的「林晚」照常在用");
    await user.click(within(dialog).getByRole("button", { name: "只改这里，下游标待更新" }));
    await waitFor(() => expect(asset("linwan")?.intent).toBe(NEW_LOOK));
    expect(productOf("linwan")?.locked_hash).toBe(before);
    expect(item(/^林晚\s*角色/)).toHaveTextContent("已锁定");
  });

  it("「撤销」 puts the locked asset's description back", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    const desc = screen.getByLabelText("描述（就是这条素材的提示词意图层）");
    const old = (desc as HTMLTextAreaElement).value;
    await user.clear(desc);
    await user.type(desc, NEW_LOOK);
    await user.tab();
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(desc).toHaveValue(old));
    expect(asset("linwan")?.intent).toBe(old);
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
    await user.click(screen.getByRole("button", { name: "用 API 出终版 · 约 $0.13" }));
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

  it("candidates are small cards; 放大 shows one at screen size, ← → the others", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/林晚出租屋/));
    const cands = screen.getByRole("radiogroup", { name: "候选" });
    expect(within(cands).getAllByRole("radio")).toHaveLength(4);
    await user.click(within(cands).getByRole("button", { name: "放大看：v1 · B" }));
    const box = await screen.findByRole("dialog", { name: "v1 · B" });
    expect(within(box).getByRole("img", { name: "v1 · B" })).toBeInTheDocument();
    expect(box).toHaveTextContent("2 / 4");
    await user.keyboard("{ArrowRight}");
    expect(await screen.findByRole("dialog", { name: "v1 · C" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "上一张" }));
    expect(await screen.findByRole("dialog", { name: "v1 · B" })).toBeInTheDocument();
    // Zooming is not picking.
    expect(asset("room")?.pick).toBe(0);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("a locked character shows the views drawn from it; a view opens at screen size", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    const views = await screen.findByRole("region", { name: "补视图" });
    // One expression a picture (Kelvin 2026-10-21): side, back and four expressions.
    for (const name of ["侧面", "背面", "平静", "微笑", "愤怒", "难过"])
      expect(await within(views).findByRole("img", { name })).toBeInTheDocument();
    await user.click(within(views).getByRole("button", { name: "放大看：背面" }));
    expect(await screen.findByRole("dialog", { name: "背面" })).toHaveTextContent("2 / 6");
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

  it("「全部配音」 shows the estimate first, then dubs every line; the voice lists them", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    expect(await screen.findByText("台词配音 0 / 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "全部配音" }));
    const dialog = await screen.findByRole("dialog", { name: "给第 1 集配音" });
    expect(dialog).toHaveTextContent("要配 2 句台词，约 $0.0006。");
    expect(fakeDub.takes).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "开始配音" }));
    expect(await screen.findByText("台词配音 2 / 2")).toBeInTheDocument();
    expect(fakeDub.takes).toEqual(["demo-b5", "demo-b10"]);
    const all = screen.getByRole("button", { name: "全部配音" });
    expect(all).toBeDisabled();
    expect(all).toHaveAttribute("title", "这一集的台词都配好了");

    await user.click(item(/^林晚\s*音色/));
    const lines = await screen.findByRole("region", { name: "第 1 集的台词配音" });
    expect(within(lines).getByRole("button", { name: "播放：……周屿？" })).toBeInTheDocument();
    expect(within(lines).getByText("1.3 秒")).toBeInTheDocument();
    expect(within(lines).getAllByRole("button", { name: "重配" })).toHaveLength(2);
  });

  it("a line's emotion follows its tone or is chosen by hand; 配音 dubs that line", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(item(/^林晚\s*音色/));
    const lines = await screen.findByRole("region", { name: "第 1 集的台词配音" });
    expect(
      within(lines).getByText("情绪按语气自动选，可以改；改完点「重配」才用上。"),
    ).toBeInTheDocument();
    const first = (await within(lines).findAllByRole("listitem"))[0] as HTMLElement;
    expect(first).toHaveTextContent("……周屿？低声，愣住未配音");
    const emotion = within(first).getByRole("combobox", { name: "情绪" });
    expect(emotion).toHaveDisplayValue("按语气（耳语）");
    await user.selectOptions(emotion, "哭腔");
    await waitFor(() =>
      expect(fakeDub.dub.lines[0]).toMatchObject({ emotion: "crying", emotion_set: true }),
    );
    expect(emotion).toHaveDisplayValue("哭腔");
    await user.click(within(first).getByRole("button", { name: "配音" }));
    expect(
      await within(first).findByRole("button", { name: "播放：……周屿？" }),
    ).toBeInTheDocument();
    expect(fakeDub.takes).toEqual(["demo-b5"]);
    expect(within(first).getByRole("button", { name: "重配" })).toBeEnabled();
    // Back to the tone.
    await user.selectOptions(emotion, "按语气（耳语）");
    await waitFor(() =>
      expect(fakeDub.dub.lines[0]).toMatchObject({ emotion: "whisper", emotion_set: false }),
    );
  });

  it("lines wait for their voice to be locked", async () => {
    const user = userEvent.setup();
    const p = productOf("vlinwan");
    if (p) p.locked_hash = null;
    renderAssets();
    expect(await screen.findByText("林晚 的音色还没锁定，2 句先等着")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全部配音" })).toBeDisabled();
    await user.click(item(/^林晚\s*音色/));
    const lines = await screen.findByRole("region", { name: "第 1 集的台词配音" });
    expect(lines).toHaveTextContent("先锁定「林晚」的音色");
    const dub = within(lines).getAllByRole("button", { name: "配音" });
    expect(dub).toHaveLength(2);
    for (const b of dub) expect(b).toBeDisabled();
    expect(within(lines).getAllByText("音色未锁定")).toHaveLength(2);
  });

  it("「重新分析剧本」 starts the analysis job", async () => {
    const user = userEvent.setup();
    renderAssets();
    await ready();
    await user.click(screen.getByRole("button", { name: "重新分析剧本" }));
    await waitFor(() => expect(fakeAssets.analyses).toEqual(["demo-e1"]));
  });
});
