import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import StoryboardPage from "@/pages/Storyboard";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

function Page() {
  useEventStream();
  return <StoryboardPage />;
}

function renderBoard(path = "/s/demo/e/1/storyboard") {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/storyboard" element={<Page />} />
    </Routes>,
    path,
  );
}

const shot = (label: string) => getDb().shots.find((s) => s.label === label);
const cards = () => screen.getByRole("region", { name: "镜头列表" });
const card = (label: string) =>
  within(cards()).getByRole("button", { name: new RegExp(`^${label}`) });
const ready = () => screen.findByText("共 34 秒 · 用当前关键帧 + 本地临时配音 + 字幕，不花钱");

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

describe("StoryboardPage", () => {
  it("shows 9 shots, 34 s, the spec and shot 1-04 with its keyframes", async () => {
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
    expect(getDb().products["demo-p-kf-1-04"]?.adopted_version_id).not.toBeNull();
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
      await screen.findByText("当前产物 · 第 1 集分镜 · 9 个镜头 · 34 秒"),
    ).toBeInTheDocument();
  });
});
