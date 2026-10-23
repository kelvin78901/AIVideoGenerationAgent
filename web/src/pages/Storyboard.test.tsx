import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import StoryboardPage from "@/pages/Storyboard";
import { backend } from "@/test/backend";
import { fakeConfig } from "@/test/fakes/config";
import { fakeImpact } from "@/test/fakes/impact";
import { fakeShots } from "@/test/fakes/shots";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

function Page() {
  useEventStream();
  return (
    <>
      <StoryboardPage />
      <Toaster />
    </>
  );
}

function renderBoard(path = "/s/demo/e/1/storyboard") {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/storyboard" element={<Page />} />
    </Routes>,
    path,
  );
}

const shot = (label: string) => fakeShots.shots.find((s) => s.label === label);
const keyframe = (label: string) =>
  fakeShots.keyframes.find((p) => p.id === shot(label)?.keyframe_product_id);
const cards = () => screen.getByRole("region", { name: "镜头列表" });
const card = (label: string) =>
  within(cards()).getByRole("button", { name: new RegExp(`^${label}`) });
// 1-04's line is not dubbed yet: the script's 4 s and a breath each side (M4, Kelvin 2026-10-21).
const ready = () => screen.findByText("共 34.5 秒 · 用当前关键帧 + 本地临时配音 + 字幕，不花钱");

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

describe("StoryboardPage", () => {
  it("shows 9 shots, 34.5 s, the spec and shot 1-04 with its keyframes", async () => {
    renderBoard();
    await ready();
    expect(within(cards()).getAllByRole("button")).toHaveLength(9);
    expect(
      screen.getByRole("link", { name: "画幅 9:16 · 关键帧和视频按 1080×1920 出 · 改成片规格" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "镜头 1-04" })).toBeInTheDocument();
    expect(await screen.findByText("当前产物 · 镜头 1-04 关键帧 · 3 张候选")).toBeInTheDocument();
    const frames = await screen.findByRole("radiogroup", { name: "首帧" });
    expect(within(frames).getAllByRole("radio")).toHaveLength(3);
    expect(
      screen.getByText("林晚（低声，愣住）：……周屿？", { selector: "div" }),
    ).toBeInTheDocument();
  });

  it("lists the script lines the shot films, each a link to the script and the novel", async () => {
    renderBoard();
    await ready();
    const line = await screen.findByRole("link", { name: "在剧本里看：……周屿？" });
    expect(line).toHaveAttribute("href", "/s/demo/e/1/script?line=demo-b5");
    expect(line).toHaveTextContent("林晚（低声，愣住）：……周屿？");
    expect(screen.getByRole("link", { name: "原文第 2 段" })).toHaveAttribute(
      "href",
      "/s/demo/e/1/novel?para=1",
    );
  });

  it("opens with the shot a link points at (1-06 films two lines)", async () => {
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-06");
    expect(await screen.findByRole("heading", { name: "镜头 1-06" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /在剧本里看：林晚把伞靠回墙边/ })).toBeVisible();
    expect(screen.getByRole("link", { name: "在剧本里看：三年了。他凭什么。" })).toHaveAttribute(
      "href",
      "/s/demo/e/1/script?line=demo-b10",
    );
  });

  it("marks references that are not locked yet", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(card("1-05"));
    expect(screen.getByRole("link", { name: "道具 · 旧黑发圈 · 未锁定" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "角色 · 林晚" })).toBeInTheDocument();
  });

  it("continuous shots take an earlier shot's last frame (1-08 continues 1-06)", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(card("1-08"));
    expect(screen.getByText("1-06 尾帧")).toBeInTheDocument();
    expect(screen.getByText(/中间的 1-07 是插入镜头/)).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "首帧" })).toBeNull();
  });

  it("saves shot settings: type, framing, move, duration, audio", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(screen.getByRole("radio", { name: "换场" }));
    await user.click(screen.getByRole("radio", { name: "特写" }));
    await user.click(screen.getByRole("radio", { name: "跟拍" }));
    await user.click(screen.getByRole("radio", { name: "先配音再对口型" }));
    const dur = screen.getByLabelText("时长（秒）");
    await user.clear(dur);
    await user.type(dur, "5");
    await user.tab();
    await waitFor(() =>
      expect(shot("1-04")).toMatchObject({
        shot_type: "scene_change",
        framing: "closeup",
        camera_move: "follow",
        audio_mode: "tts",
        duration_s: 5,
      }),
    );
    expect(await screen.findByText(/共 35 秒/)).toBeInTheDocument();
  });

  it("moves people and the camera on the blocking plan with the keyboard", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    const plan = screen.getByRole("group", { name: "站位（俯视）" });
    const linwan = within(plan).getByRole("button", { name: /^林晚：横 62%，纵 40%/ });
    linwan.focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    await waitFor(() =>
      expect(shot("1-04")?.blocking.find((b) => b.id === "linwan")?.x).toBeCloseTo(0.66),
    );
    expect(within(plan).getByRole("button", { name: /机位 · 近景/ })).toBeInTheDocument();
  });

  it("confirms a shot; 分镜 goes to 4 / 9", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(await screen.findByRole("radio", { name: "v1 · B" }));
    await waitFor(() => expect(shot("1-04")?.keyframe_pick).toBe(1));
    await user.click(screen.getByRole("button", { name: "确认这个镜头" }));
    await waitFor(() => expect(shot("1-04")?.confirmed).toBe(true));
    expect(shot("1-04")?.keyframe_pick).toBe(1);
    expect(card("1-04")).toHaveTextContent("已确认");
    expect(screen.getByRole("radio", { name: "v1 · B" })).toBeDisabled();
    // The picked draft is locked as a pick version; the drafts stay on screen.
    expect(keyframe("1-04")).toMatchObject({ status: "locked", pick: { idx: 1 } });
    expect(keyframe("1-04")?.versions.at(-1)?.origin).toBe("pick");
    const res = await fetch(`http://localhost/api/v1/episodes/${EP1}/progress`);
    const body = (await res.json()) as { steps: { storyboard: { done: number } } };
    expect(body.steps.storyboard.done).toBe(4);
  });

  it("adds a locked asset as a reference", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(screen.getByRole("button", { name: "添加参考" }));
    await user.click(await screen.findByRole("button", { name: "道具 · 红色长柄伞" }));
    await waitFor(() => expect(shot("1-04")?.asset_ids).toContain("umbrella"));
  });

  it("plays the preview through the shots", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(screen.getByRole("button", { name: "播放预演" }));
    expect(screen.getByTestId("preview-caption")).toHaveTextContent("楼道全景");
    await waitFor(
      () => expect(screen.getByTestId("preview-caption")).toHaveTextContent("门口的红伞"),
      {
        timeout: 1500,
      },
    );
    await user.click(screen.getByRole("button", { name: "暂停预演" }));
  });

  it("the run bar follows the Inspector: 分镜规划", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(screen.getByRole("button", { name: "分镜规划" }));
    expect(
      await screen.findByText("当前产物 · 第 1 集分镜 · 9 个镜头 · 34.5 秒"),
    ).toBeInTheDocument();
  });

  it("shows each keyframe candidate's picture; 放大 opens it at screen size", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    const frames = await screen.findByRole("radiogroup", { name: "首帧" });
    const draft = keyframe("1-04")?.versions.at(-1);
    const sha = draft?.files.find((f) => f.idx === 1)?.sha256 ?? "";
    expect(within(frames).getByRole("img", { name: "v1 · B" })).toHaveAttribute(
      "src",
      `/api/v1/files/${sha}`,
    );
    expect(within(frames).getAllByText("本地草稿")).toHaveLength(3);
    await user.click(within(frames).getByRole("button", { name: "放大看：v1 · B" }));
    expect(await screen.findByRole("dialog", { name: "v1 · B" })).toHaveTextContent("2 / 3");
    // Zooming is not picking.
    expect(shot("1-04")?.keyframe_pick).toBe(0);
  });

  it("「用 API 出终版」 makes one picture from the picked draft", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(await screen.findByRole("radio", { name: "v1 · C" }));
    await waitFor(() => expect(shot("1-04")?.keyframe_pick).toBe(2));
    const draft = keyframe("1-04")?.versions.at(-1);
    await user.click(screen.getByRole("button", { name: "用 API 出终版 · 约 $0.13" }));
    await waitFor(() => expect(keyframe("1-04")?.versions).toHaveLength(2));
    const final = keyframe("1-04")?.versions.at(-1);
    expect(final).toMatchObject({ stage: "final", parent_version_id: draft?.id });
    expect(final?.model_key).toBe("google/nano-banana-pro");
    expect(await screen.findByRole("radio", { name: "v2 · A" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByText("API 终版")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /用 API 出终版/ })).not.toBeInTheDocument();
  });

  it("taking a confirmation back unlocks the keyframe", async () => {
    const user = userEvent.setup();
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-01");
    expect(await screen.findByRole("heading", { name: "镜头 1-01" })).toBeInTheDocument();
    expect(keyframe("1-01")?.locked_hash).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "取消确认" }));
    await waitFor(() => expect(shot("1-01")?.confirmed).toBe(false));
    expect(keyframe("1-01")?.locked_hash).toBeNull();
    expect(await screen.findByText("已取消确认 1-01。")).toBeInTheDocument();
  });

  it("a shot without a keyframe cannot be confirmed yet", async () => {
    const user = userEvent.setup();
    const kf = keyframe("1-05");
    if (kf) Object.assign(kf, { versions: [], current_version_id: null, status: "empty" });
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-05");
    expect(
      await screen.findByText("这个镜头还没有关键帧。在右侧选「关键帧」组件后点「重跑」。"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认这个镜头" }));
    expect(await screen.findByText("这个镜头还没有关键帧：先出一版再确认")).toBeInTheDocument();
    expect(shot("1-05")?.confirmed).toBe(false);
  });

  it("changing a confirmed shot shows the impact first; 只改这里 writes it and takes it back", async () => {
    const user = userEvent.setup();
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-02");
    expect(await screen.findByRole("heading", { name: "镜头 1-02" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "近景" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("镜头 1-02 已确认，改动会影响下游");
    expect(dialog).toHaveTextContent("镜头 1-02 会取消确认：改完要重新确认");
    // Nothing is written while the dialog is open.
    expect(shot("1-02")).toMatchObject({ framing: "medium", confirmed: true });
    await user.click(within(dialog).getByRole("button", { name: "只改这里，下游标待更新" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(fakeImpact.applied).toEqual([
      { kind: "shot_edit", target_id: "demo-shot-1-02", action: "mark" },
    ]);
    expect(shot("1-02")).toMatchObject({ framing: "close", confirmed: false });
    expect(await screen.findByRole("button", { name: "确认这个镜头" })).toBeInTheDocument();
  });

  it("「撤销」 leaves a confirmed shot's description as it was", async () => {
    const user = userEvent.setup();
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-03");
    expect(await screen.findByRole("heading", { name: "镜头 1-03" })).toBeInTheDocument();
    const desc = screen.getByLabelText("画面描述（关键帧提示词的意图层）");
    const before = shot("1-03")?.intent ?? "";
    await user.clear(desc);
    await user.type(desc, "便利贴特写，字迹被雨水晕开。");
    await user.tab();
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("便利贴特写，字迹被雨水晕开。");
    expect(dialog).toHaveTextContent("关键帧 · 镜头 1-03 按新的画面描述重出候选");
    await user.click(within(dialog).getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(shot("1-03")).toMatchObject({ intent: before, confirmed: true });
    expect(screen.getByLabelText("画面描述（关键帧提示词的意图层）")).toHaveValue(before);
  });

  it("the Inspector's per-shot settings are the shot's (by id, as runs read them)", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(await screen.findByRole("radio", { name: "本地" }));
    await waitFor(() => expect(fakeConfig.item["kf|shot:demo-shot-1-04"]?.mode).toBe("local"));
  });

  it("shows the shots as a table; a cell saves its setting; the row's shot is the board's", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    await user.click(screen.getByRole("radio", { name: "表格" }));
    const table = await screen.findByRole("region", { name: "镜头表" });
    expect(within(table).getAllByRole("row")).toHaveLength(10);
    expect(within(table).getByText("接 1-06 尾帧")).toBeInTheDocument();
    await user.selectOptions(within(table).getByLabelText("镜头 1-05 的景别"), "近景");
    await waitFor(() => expect(shot("1-05")?.framing).toBe("close"));
    await user.click(within(table).getByRole("button", { name: "1-07" }));
    expect(await screen.findByRole("heading", { name: "镜头 1-07" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "分镜板" }));
    expect(screen.getByRole("heading", { name: "镜头 1-07" })).toBeInTheDocument();
    expect(card("1-07")).toHaveAttribute("aria-pressed", "true");
  });

  it("a dialogue shot runs as long as its audio; longer by hand, then back to the audio", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    expect(screen.getByText("按台词音频算（含前后留白），最短 4.5 秒")).toBeInTheDocument();
    const dur = screen.getByLabelText("时长（秒）");
    await user.clear(dur);
    await user.type(dur, "6");
    await user.tab();
    await waitFor(() => expect(shot("1-04")).toMatchObject({ duration_s: 6, manual_s: 6 }));
    expect(await screen.findByText("手动设定 · 不能短于台词音频 4.5 秒")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "恢复按音频" }));
    await waitFor(() =>
      expect(shot("1-04")).toMatchObject({
        duration_s: 4.5,
        manual_s: null,
        duration_source: "audio",
      }),
    );
  });

  it("a length shorter than the audio is refused and put back", async () => {
    const user = userEvent.setup();
    renderBoard();
    await ready();
    const dur = screen.getByLabelText("时长（秒）");
    await user.clear(dur);
    await user.type(dur, "3");
    await user.tab();
    expect(await screen.findByText("不能短于台词音频：至少 4.5 秒")).toBeInTheDocument();
    expect(shot("1-04")?.duration_s).toBe(4.5);
    await waitFor(() => expect(screen.getByLabelText("时长（秒）")).toHaveValue(4.5));
  });

  it("longer than one video take suggests splitting the shot", async () => {
    const s = shot("1-08");
    if (s) Object.assign(s, { duration_s: 16, manual_s: 16, split_hint: true });
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-08");
    expect(await screen.findByText("超过 15 秒（视频单段上限），建议拆镜")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "恢复规划的 6 秒" })).toBeInTheDocument();
  });

  it("splits a shot after a line it films, then merges it back", async () => {
    const user = userEvent.setup();
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-06");
    expect(await screen.findByRole("heading", { name: "镜头 1-06" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "拆分" }));
    await user.click(await screen.findByRole("button", { name: /^在「林晚把伞靠回墙边/ }));
    expect(await screen.findByText("已拆分：1-06 后面多了 1-07")).toBeInTheDocument();
    expect(fakeShots.shots).toHaveLength(10);
    expect(shot("1-07")?.line_ids).toEqual(["demo-b10"]);
    // What continued 1-06 now continues its second half.
    expect(shot("1-09")?.tail_from).toBe("1-07");
    await user.click(screen.getByRole("button", { name: "和下一个合并" }));
    expect(await screen.findByText("已把下一个镜头并进 1-06")).toBeInTheDocument();
    expect(fakeShots.shots).toHaveLength(9);
    expect(shot("1-06")?.line_ids).toEqual(["demo-b8", "demo-b10"]);
  });

  it("the last shot of a scene has nothing to merge with", async () => {
    renderBoard("/s/demo/e/1/storyboard?shot=demo-shot-1-05");
    expect(await screen.findByRole("heading", { name: "镜头 1-05" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "和下一个合并" })).toBeDisabled();
  });

  it("merging confirmed shots in the table shows the impact first", async () => {
    const user = userEvent.setup();
    renderBoard("/s/demo/e/1/storyboard?view=table");
    const table = await screen.findByRole("region", { name: "镜头表" });
    await user.click(within(table).getByRole("button", { name: "把镜头 1-01 和下一个合并" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("镜头 1-01、1-02 会取消确认");
    expect(fakeShots.shots).toHaveLength(9);
    await user.click(within(dialog).getByRole("button", { name: "只改这里，下游标待更新" }));
    await waitFor(() => expect(fakeShots.shots).toHaveLength(8));
    expect(shot("1-01")).toMatchObject({ confirmed: false, line_ids: ["demo-b2", "demo-b3"] });
  });
});
