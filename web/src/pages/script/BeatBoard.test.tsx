import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import ScriptPage from "@/pages/Script";
import { backend, fake } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { fakeBible } from "@/test/fakes/bible";
import { fakeEpisodes } from "@/test/fakes/episodes";
import { renderAt } from "@/test/render";

function Page() {
  useEventStream();
  return (
    <>
      <ScriptPage />
      <Toaster />
    </>
  );
}

function renderScript(series = "demo") {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/script" element={<Page />} />
    </Routes>,
    `/s/${series}/e/1/script`,
  );
}

const column = (name: RegExp) => screen.getByRole("listitem", { name });
const columns = () => screen.getAllByRole("listitem", { name: /^第 \d 集《/ });
const beats = (name: RegExp) =>
  within(column(name))
    .getAllByRole("button", { name: /^改节拍/ })
    .map((b) => b.textContent);
const beatEl = (id: string) => document.querySelector(`[data-beat="${id}"]`) as HTMLElement;
const dataTransfer = () => ({ setData: vi.fn(), effectAllowed: "", dropEffect: "" });

async function openBoard(user: ReturnType<typeof userEvent.setup>) {
  renderScript();
  await user.click(await screen.findByRole("radio", { name: "节拍看板" }));
  return screen.getByRole("list", { name: "节拍看板" });
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

describe("节拍看板", () => {
  it("one column per episode, the emotion curve above, 分集规划 in the run bar", async () => {
    const user = userEvent.setup();
    const board = await openBoard(user);
    expect(board).toBeInTheDocument();
    const names = columns().map((c) => c.getAttribute("aria-label"));
    expect(names).toEqual(["第 1 集《红伞》", "第 2 集《十二点》", "第 3 集《旧发圈》"]);
    const ep1 = column(/第 1 集/);
    expect(ep1).toHaveTextContent("5 个节拍 · 约 0:34 · 场 1–2");
    expect(ep1).toHaveTextContent("钩子：门口那把红伞，和三年没见的字迹。");
    expect(ep1).toHaveTextContent("卡点：她拿起了那把伞");
    expect(beats(/第 1 集/)[2]).toBe("3便利贴只有一句：楼下便利店，等你到十二点。情绪 +0.4");
    expect(beats(/第 2 集/)).toHaveLength(9);
    expect(await screen.findByText("当前产物 · 分集方案 · 3 集")).toBeInTheDocument();

    const curve = screen.getByRole("region", { name: "全剧情绪曲线" });
    const points = within(curve).getAllByRole("button", { name: /^第 \d 集节拍/ });
    expect(points).toHaveLength(22);
    expect(within(curve).getByText("把鼠标移到曲线上看每个节拍")).toBeInTheDocument();
    await user.hover(points[13] as HTMLElement);
    expect(within(curve).getByText("第 2 集 · 节拍 9")).toBeInTheDocument();
    expect(within(curve).getByText(/便利店里没有他。 · 情绪 −0.9/)).toBeInTheDocument();
    await user.click(within(curve).getByRole("radio", { name: "表" }));
    const table = within(curve).getByRole("table", { name: "全剧情绪曲线（表）" });
    expect(within(table).getAllByRole("row")).toHaveLength(23);
  });

  it("drags a beat to the start of the next episode", async () => {
    const user = userEvent.setup();
    await openBoard(user);
    fireEvent.dragStart(beatEl("demo-bt5"), { dataTransfer: dataTransfer() });
    fireEvent.dragOver(beatEl("demo-bt6"), { dataTransfer: dataTransfer() });
    expect(document.querySelectorAll("[data-drop-marker]")).toHaveLength(1);
    fireEvent.drop(beatEl("demo-bt6"), { dataTransfer: dataTransfer() });
    expect(await screen.findByText("已把节拍移到第 2 集第 1 个。")).toBeInTheDocument();
    expect(fakeEpisodes.beatPatches).toEqual([
      { id: "demo-bt5", position: 0, episode_id: "demo-e2" },
    ]);
    await waitFor(() => expect(beats(/第 1 集/)).toHaveLength(4));
    expect(beats(/第 2 集/)[0]).toBe("1她还是拿起了那把伞。情绪 +0.5");
    expect(column(/第 2 集/)).toHaveTextContent("10 个节拍");
  });

  it("dropping a beat where it already is sends nothing", async () => {
    const user = userEvent.setup();
    await openBoard(user);
    fireEvent.dragStart(beatEl("demo-bt2"), { dataTransfer: dataTransfer() });
    fireEvent.dragOver(beatEl("demo-bt3"), { dataTransfer: dataTransfer() });
    fireEvent.drop(beatEl("demo-bt3"), { dataTransfer: dataTransfer() });
    expect(fakeEpisodes.beatPatches).toEqual([]);
  });

  it("a refused move goes back", async () => {
    const user = userEvent.setup();
    fakeEpisodes.failWith = { status: 409, code: "product_busy" };
    await openBoard(user);
    fireEvent.dragStart(beatEl("demo-bt1"), { dataTransfer: dataTransfer() });
    const end = within(column(/第 3 集/)).getByText("拖到这里放在最后");
    fireEvent.dragOver(end, { dataTransfer: dataTransfer() });
    fireEvent.drop(end, { dataTransfer: dataTransfer() });
    // Put back when the backend says no.
    expect(await screen.findByText("这一步正在生成，等它跑完再试")).toBeInTheDocument();
    expect(fakeEpisodes.beatPatches).toEqual([
      { id: "demo-bt1", position: 8, episode_id: "demo-e3" },
    ]);
    await waitFor(() => expect(beats(/第 1 集/)).toHaveLength(5));
    expect(beats(/第 3 集/)).toHaveLength(8);
  });

  it("edits a beat's text and moves it with the dialog", async () => {
    const user = userEvent.setup();
    await openBoard(user);
    await user.click(screen.getByRole("button", { name: /^改节拍 1-4：/ }));
    const dialog = screen.getByRole("dialog", { name: "改节拍" });
    const text = within(dialog).getByLabelText("节拍");
    await user.clear(text);
    await user.type(text, "她把伞靠回墙边，又拿起来。");
    await user.selectOptions(within(dialog).getByLabelText("所在的集"), "demo-e2");
    await user.click(within(dialog).getByRole("button", { name: "保存" }));
    expect(await screen.findByText("已把节拍移到第 2 集第 10 个。")).toBeInTheDocument();
    expect(fakeEpisodes.beatPatches).toEqual([
      { id: "demo-bt4", text: "她把伞靠回墙边，又拿起来。", episode_id: "demo-e2" },
    ]);
    await waitFor(() => expect(beats(/第 2 集/).at(-1)).toMatch(/^10她把伞靠回墙边，又拿起来。/));
  });

  it("edits an episode's title, hook and cliffhanger", async () => {
    const user = userEvent.setup();
    await openBoard(user);
    await user.click(screen.getByRole("button", { name: "改第 3 集的集名、钩子和卡点" }));
    const dialog = screen.getByRole("dialog", { name: "改第 3 集" });
    const title = within(dialog).getByLabelText("集名");
    await user.clear(title);
    await user.type(title, "雨停之前");
    await user.click(within(dialog).getByRole("button", { name: "保存" }));
    expect(await screen.findByText("已保存。")).toBeInTheDocument();
    expect(fakeEpisodes.episodePatches).toEqual([{ id: "demo-e3", title: "雨停之前" }]);
    expect(
      await screen.findByRole("listitem", { name: "第 3 集《雨停之前》" }),
    ).toBeInTheDocument();
  });

  it("is read-only while 分集规划 is locked", async () => {
    const user = userEvent.setup();
    const split = fakeBible.products.find((p) => p.component_id === "split");
    if (split) split.status = "locked";
    await openBoard(user);
    expect(screen.getByText("分集规划已锁定，节拍改不了。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^改节拍 1-1：/ })).toBeDisabled();
    expect(beatEl("demo-bt1")).toHaveAttribute("draggable", "false");
    expect(screen.getByRole("button", { name: "改第 1 集的集名、钩子和卡点" })).toBeDisabled();
  });

  it("a series without a plan shows how to start", async () => {
    fake.created.push({
      id: "s1",
      slug: "s1",
      title: "新剧",
      ui_lang: "zh-CN",
      created_at: "2026-10-19T10:00:00Z",
    });
    renderScript("s1");
    expect(await screen.findByText("还没有分集")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始分集规划" })).toBeDisabled();
    expect(screen.queryByRole("radio", { name: "节拍看板" })).not.toBeInTheDocument();
  });
});
