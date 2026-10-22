import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import ScriptPage from "@/pages/Script";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { fakeEpisodes } from "@/test/fakes/episodes";
import { dubFakeEpisode } from "@/test/fakes/dub";
import { fakeImpact } from "@/test/fakes/impact";
import { fakeScript } from "@/test/fakes/script";
import { renderAt } from "@/test/render";

// The user's own edit (content, not UI copy).
const EDITED = "门口斜靠着一把红伞。";

function Page() {
  useEventStream();
  return <ScriptPage />;
}

function renderScript(path = "/s/demo/e/1/script") {
  return renderAt(
    <>
      <Routes>
        <Route path="/s/:series/e/:ep/script" element={<Page />} />
      </Routes>
      <Toaster />
    </>,
    path,
  );
}

const lineOf = (id: string) => fakeScript.scripts[EP1]?.lines.find((l) => l.id === id);
const block = (text: RegExp) => screen.getByRole("button", { name: text, pressed: false });
const stale = () => getDb().progress[EP1]?.steps;
const META = "2 场 · 12 段 · 其中 AI 新增 2 段";

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  demoTiming.runMs = 20;
});
afterEach(() => {
  vi.unstubAllGlobals();
  demoTiming.runMs = 1400;
});

describe("ScriptPage", () => {
  it("shows the episodes, the script and its counts", async () => {
    renderScript();
    expect(await screen.findByText(META)).toBeInTheDocument();
    const ep1 = screen.getByRole("link", { name: /第 1 集《红伞》/ });
    expect(ep1).toHaveAttribute("aria-current", "page");
    expect(ep1).toHaveTextContent("场 1–2 · 9 个镜头 · 约 0:34");
    expect(ep1).toHaveTextContent("卡点：她拿起了那把伞");
    // The seeded demo has episode 1's script gate confirmed.
    expect(ep1).toHaveTextContent("剧本已确认");
    // The plan is the backend's (分集规划): episode 3 has its cliffhanger too.
    expect(screen.getByRole("link", { name: /第 3 集/ })).toHaveTextContent(
      "场 5–7 · 约 1:20卡点：红伞底下，雨还没有停",
    );
    expect(screen.getByText("当前产物 · 第 1 集剧本 · 场 1–2 · 12 段")).toBeInTheDocument();
    // Scene numbers are the backend's count, shown in front of the heading.
    expect(block(/^场 2\s夜\s内\s林晚出租屋/)).toBeInTheDocument();
    expect(screen.getAllByText("AI 新增")).toHaveLength(2);
    expect(screen.getByText("本集卡点")).toBeInTheDocument();
    // The first line uses the accepted addition (林晚's coat).
    expect(screen.getByRole("button", { name: /声控灯坏了一半/ })).toHaveTextContent(
      "原文第 1 段 · 补写",
    );
  });

  it("lights up the source paragraphs of the selected block and links to the novel and shots", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(block(/特写：便利贴/));
    const source = screen.getByRole("region", { name: "原文（已采纳补写）" });
    const lit = within(source)
      .getAllByRole("listitem")
      .map((li) => li.hasAttribute("data-lit"));
    expect(lit).toEqual([false, false, true, false, false]);
    expect(screen.getByRole("link", { name: "来自原文第 3 段" })).toHaveAttribute(
      "href",
      "/s/demo/e/1/novel?para=2",
    );
    expect(screen.getByRole("link", { name: "镜头 1-03" })).toHaveAttribute(
      "href",
      "/s/demo/e/1/storyboard?shot=demo-shot-1-03",
    );
    // The voice-over is laid over 1-06, which also films 林晚 at the door.
    await user.click(block(/三年了/));
    expect(screen.getByRole("link", { name: "镜头 1-06" })).toBeInTheDocument();
  });

  it("opens with the line a link points at", async () => {
    renderScript("/s/demo/e/1/script?line=demo-b10");
    expect(await screen.findByRole("button", { name: /三年了/, pressed: true })).toBeVisible();
  });

  it("shows the lines as a table", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(screen.getByRole("radio", { name: "结构化表格" }));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(11); // header + 10 lines
    expect(rows[4]).toHaveTextContent("台词");
    expect(rows[4]).toHaveTextContent("低声，愣住");
    expect(rows[8]).toHaveTextContent("叠在 1-06");
  });

  it("before dubbing, a scene adds up its lines' estimates; nothing plays", async () => {
    renderScript();
    await screen.findByText(META);
    // Before dubbing: the script's estimate.
    expect(await screen.findByText("台词 4.0 秒 · 已配音 0 / 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^播放/ })).not.toBeInTheDocument();
  });

  it("after dubbing, lines play in both views with their real length", async () => {
    const user = userEvent.setup();
    dubFakeEpisode();
    renderScript();
    await screen.findByText(META);
    expect(await screen.findByText("台词 1.3 秒 · 已配音 1 / 1")).toBeInTheDocument();
    expect(screen.getByText("台词 2.3 秒 · 已配音 1 / 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "播放：……周屿？" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "播放：三年了。他凭什么。" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "结构化表格" }));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    const row = rows[4] as HTMLElement;
    expect(row).toHaveTextContent("1.3 秒");
    expect(within(row).getByRole("button", { name: "播放：……周屿？" })).toBeInTheDocument();
    expect(rows[8]).toHaveTextContent("2.3 秒叠在 1-06");
  });

  it("editing a confirmed line previews the impact; 只改这里 saves it and marks 待更新", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(block(/门口靠着一把红色长柄伞/));
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const box = screen.getByLabelText("编辑这一段（保存后会显示影响范围）");
    await user.clear(box);
    await user.type(box, EDITED);
    await user.click(screen.getByRole("button", { name: "保存" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(`改的是：△ ${EDITED}`);
    // The backend's line, then the demo's downstream of the script.
    expect(dialog).toHaveTextContent("已确认的第 1 集剧本会改成新内容");
    expect(dialog).toHaveTextContent("素材 · 道具「红色长柄伞、黄色便利贴」");
    expect(dialog).toHaveTextContent("视频 · 1-02（已采纳）");
    // Nothing is saved while the dialog is open.
    expect(lineOf("demo-b3")?.edited).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "只改这里，下游标待更新" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    // The backend saved it (/impact/apply); the demo marks the later steps.
    expect(fakeImpact.applied).toEqual([
      { kind: "line_edit", target_id: "demo-b3", action: "mark" },
    ]);
    expect(lineOf("demo-b3")).toMatchObject({ text: EDITED, edited: true });
    expect(stale()?.assets.stale).toBe(2);
    expect(stale()?.storyboard.stale).toBe(1);
    expect(stale()?.generate.stale).toBe(1);
    expect(
      await screen.findByRole("button", { name: new RegExp(EDITED), pressed: true }),
    ).toHaveTextContent("已修改");
  });

  it("「撤销」 keeps the confirmed text", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(block(/门口靠着一把红色长柄伞/));
    await user.click(screen.getByRole("button", { name: "编辑" }));
    await user.type(screen.getByLabelText(/编辑这一段/), "！");
    await user.click(screen.getByRole("button", { name: "保存" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(fakeScript.patches).toEqual([]);
    expect(fakeImpact.applied.map((a) => a.action)).toEqual(["undo"]);
    expect(lineOf("demo-b3")?.edited).toBe(false);
    expect(stale()?.assets.stale).toBe(0);
    expect(screen.getByRole("button", { name: /门口靠着一把红色长柄伞/ })).not.toHaveTextContent(
      "已修改",
    );
  });

  it("a draft script is edited in place, without the impact dialog", async () => {
    const ep1 = fakeEpisodes.list.find((e) => e.id === EP1);
    if (ep1) ep1.script_status = "draft"; // the gate reopened: 剧本草稿
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(block(/^场 2\s/));
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const box = screen.getByLabelText("编辑这一段");
    await user.clear(box);
    await user.type(box, "夜　内　出租屋门内");
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText("已保存。")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(fakeScript.patches).toEqual([{ id: "demo-b7", heading: "夜　内　出租屋门内" }]);
    expect(screen.getByRole("button", { name: /^场 2\s夜\s内\s出租屋门内/ })).toHaveTextContent(
      "已修改",
    );
  });

  it("「重写这一段」 proposes a rewrite; 确认并同步 saves it", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(block(/周屿？/));
    await user.click(screen.getByRole("button", { name: "重写这一段" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("改的是：林晚（低声，愣住）：……是你啊。");
    await user.click(within(dialog).getByRole("button", { name: "确认并同步 · 预计 $0.33" }));
    await waitFor(() => expect(lineOf("demo-b5")?.text).toBe("……是你啊。"));
    expect(await screen.findByText(/已开始同步/)).toBeInTheDocument();
  });

  it("a rewrite over the budget waits for the user's yes", async () => {
    fakeScript.overBudget = true;
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(block(/周屿？/));
    await user.click(screen.getByRole("button", { name: "重写这一段" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("预计 $0.9，超过上限 $0.8，确认后才会发出");
    await user.click(within(alert).getByRole("button", { name: "仍然重写" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("……是你啊。");
    expect(fakeScript.rewrites.map((r) => r.confirm_budget)).toEqual([false, true]);
  });

  it("「换模型重写」 rewrites with the picked model", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText(META);
    await user.click(block(/手机亮屏/));
    await user.click(screen.getByRole("button", { name: "换模型重写" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByRole("menuitem", { name: /DeepSeek V4 Pro/ })).toBeNull();
    await user.click(within(menu).getByRole("menuitem", { name: /Kimi K2.6/ }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("没有新消息");
    expect(fakeScript.rewrites.at(-1)).toMatchObject({
      id: "demo-b9",
      model: "moonshot/kimi-k2.6",
    });
  });

  it("says when the script on screen is not adopted", async () => {
    const script = fakeScript.scripts[EP1];
    if (script) script.adopted = false;
    renderScript();
    expect(
      await screen.findByText(
        "剧本化有一版新结果还没采纳：这里显示的是它，在「历史」里采纳后下游才会用。",
      ),
    ).toBeInTheDocument();
  });

  it("generates the script of an episode that has none", async () => {
    const user = userEvent.setup();
    renderScript("/s/demo/e/2/script");
    expect(await screen.findByText(/这一集的剧本还没生成/)).toBeInTheDocument();
    expect(screen.getByText("当前产物 · 第 2 集剧本 · 还没生成")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "生成这一集的剧本" }));
    expect(await screen.findByRole("heading", { name: "第 2 集剧本" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /第 2 集《十二点》/ })).toHaveTextContent("剧本草稿");
    expect(screen.queryByText(/这一集的剧本还没生成/)).not.toBeInTheDocument();
  });

  it("the run bar follows the Inspector: 分集规划 shows the episode plan", async () => {
    const user = userEvent.setup();
    renderScript();
    await screen.findByText("当前产物 · 第 1 集剧本 · 场 1–2 · 12 段");
    expect(screen.getByText(/v2 · Kimi K2.6/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "分集规划" }));
    expect(await screen.findByText("当前产物 · 分集方案 · 3 集")).toBeInTheDocument();
    expect(screen.getByText(/v1 · DeepSeek V4.1 Flash/)).toBeInTheDocument();
  });
});
