import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import ScriptPage from "@/pages/Script";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

// The user's own edit (content, not UI copy).
const EDITED = "门口斜靠着一把红伞。";

function Page() {
  useEventStream();
  return <ScriptPage />;
}

function renderScript(ep = 1) {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/script" element={<Page />} />
    </Routes>,
    `/s/demo/e/${ep}/script`,
  );
}

const lineOf = (id: string) => getDb().scripts[EP1]?.lines.find((l) => l.id === id);
const block = (text: RegExp) => screen.getByRole("button", { name: text, pressed: false });
const stale = () => getDb().progress[EP1]?.steps;

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  demoTiming.runMs = 20;
  demoTiming.rewriteMs = 10;
});
afterEach(() => {
  vi.unstubAllGlobals();
  demoTiming.runMs = 1400;
  demoTiming.rewriteMs = 1100;
});

describe("ScriptPage", () => {
  it("shows the episodes, the script and its counts", async () => {
    renderScript();
    expect(await screen.findByText("2 场 · 12 段 · 其中 AI 新增 2 段")).toBeInTheDocument();
    const ep1 = screen.getByRole("link", { name: /第 1 集《红伞》/ });
    expect(ep1).toHaveAttribute("aria-current", "page");
    expect(ep1).toHaveTextContent("场 1–2 · 9 个镜头 · 约 0:34");
    expect(ep1).toHaveTextContent("卡点：她拿起了那把伞");
    expect(ep1).toHaveTextContent("剧本已确认");
    // The plan is the backend's (分集规划): episode 3 has its cliffhanger too.
    expect(screen.getByRole("link", { name: /第 3 集/ })).toHaveTextContent(
      "场 5–7 · 约 1:20卡点：红伞底下，雨还没有停",
    );
    expect(screen.getByText("当前产物 · 第 1 集剧本 · 场 1–2 · 12 段")).toBeInTheDocument();
    expect(screen.getAllByText("AI 新增")).toHaveLength(2);
    expect(screen.getByText("本集卡点")).toBeInTheDocument();
  });

  it("lights up the source paragraphs of the selected block", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("2 场 · 12 段 · 其中 AI 新增 2 段");
    await user.click(block(/特写：便利贴/));
    const source = screen.getByRole("region", { name: "原文（已采纳补写）" });
    const lit = within(source)
      .getAllByRole("listitem")
      .map((li) => li.hasAttribute("data-lit"));
    expect(lit).toEqual([false, false, true, false, false]);
    expect(screen.getByText("来自原文第 3 段")).toBeInTheDocument();
  });

  it("shows the lines as a table", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("2 场 · 12 段 · 其中 AI 新增 2 段");
    await user.click(screen.getByRole("radio", { name: "结构化表格" }));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(11); // header + 10 lines
    expect(rows[4]).toHaveTextContent("台词");
    expect(rows[4]).toHaveTextContent("低声，愣住");
    expect(rows[8]).toHaveTextContent("叠在 1-06");
  });

  it("editing a confirmed line previews the impact; 只标记 saves it and marks 待更新", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("2 场 · 12 段 · 其中 AI 新增 2 段");
    await user.click(block(/门口靠着一把红色长柄伞/));
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const box = screen.getByLabelText("编辑这一段（保存后会显示影响范围）");
    await user.clear(box);
    await user.type(box, EDITED);
    await user.click(screen.getByRole("button", { name: "保存" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(`改的是：△ ${EDITED}`);
    expect(dialog).toHaveTextContent("素材 · 道具「红色长柄伞、黄色便利贴」");
    expect(dialog).toHaveTextContent("视频 · 1-02（已采纳）");
    // Nothing is saved while the dialog is open.
    expect(lineOf("demo-b3")?.edited).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "只标记待更新" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(lineOf("demo-b3")).toMatchObject({ text: EDITED, edited: true });
    expect(stale()?.assets.stale).toBe(2);
    expect(stale()?.storyboard.stale).toBe(1);
    expect(stale()?.generate.stale).toBe(1);
    expect(screen.getByRole("button", { name: new RegExp(EDITED) })).toHaveTextContent("已修改");
  });

  it("「撤销修改」 keeps the confirmed text", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("2 场 · 12 段 · 其中 AI 新增 2 段");
    await user.click(block(/门口靠着一把红色长柄伞/));
    await user.click(screen.getByRole("button", { name: "编辑" }));
    await user.type(screen.getByLabelText(/编辑这一段/), "！");
    await user.click(screen.getByRole("button", { name: "保存" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "撤销修改" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(lineOf("demo-b3")?.edited).toBe(false);
    expect(stale()?.assets.stale).toBe(0);
    expect(screen.getByRole("button", { name: /门口靠着一把红色长柄伞/ })).not.toHaveTextContent(
      "已修改",
    );
  });

  it("「重写这一段」 proposes a rewrite; 自动重跑 saves it", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("2 场 · 12 段 · 其中 AI 新增 2 段");
    await user.click(block(/周屿？/));
    await user.click(screen.getByRole("button", { name: "重写这一段" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("改的是：林晚（低声，愣住）：……是你啊。");
    await user.click(
      within(dialog).getByRole("button", { name: "自动重跑受影响的部分 · 预计 $0.33" }),
    );
    await waitFor(() => expect(lineOf("demo-b5")?.text).toBe("……是你啊。"));
  });

  it("「换模型重写」 rewrites with the picked model", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("2 场 · 12 段 · 其中 AI 新增 2 段");
    await user.click(block(/手机亮屏/));
    await user.click(screen.getByRole("button", { name: "换模型重写" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByRole("menuitem", { name: /DeepSeek V4 Pro/ })).toBeNull();
    await user.click(within(menu).getByRole("menuitem", { name: /Kimi K2.6/ }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("没有新消息");
  });

  it("generates the script of an episode that has none", async () => {
    const user = userEvent.setup();
    renderScript(2);
    expect(await screen.findByText(/这一集的剧本还没生成/)).toBeInTheDocument();
    expect(screen.getByText("当前产物 · 第 2 集剧本 · 还没生成")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "生成这一集的剧本" }));
    expect(await screen.findByText(/剧本草稿已生成/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /第 2 集《十二点》/ })).toHaveTextContent("剧本草稿");
    expect(screen.getByRole("button", { name: "重新生成这一集" })).toBeInTheDocument();
  });

  it("the run bar follows the Inspector: 分集规划 shows the episode plan", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("当前产物 · 第 1 集剧本 · 场 1–2 · 12 段");
    await user.click(screen.getByRole("button", { name: "分集规划" }));
    expect(await screen.findByText("当前产物 · 分集方案 · 3 集")).toBeInTheDocument();
    expect(screen.getByText(/v1 · DeepSeek V4.1 Flash/)).toBeInTheDocument();
  });
});
