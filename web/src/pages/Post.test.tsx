import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { getDb } from "@/mocks/db";
import PostPage from "@/pages/Post";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

function Page() {
  useEventStream();
  return (
    <>
      <PostPage />
      <Toaster />
    </>
  );
}

function renderPost() {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/post" element={<Page />} />
    </Routes>,
    "/s/demo/e/1/post",
  );
}

const timeline = () => screen.getByRole("region", { name: "时间线" });
const segment = (name: string | RegExp) => within(timeline()).getByRole("button", { name });
const ready = () => screen.findByRole("heading", { name: "片段 1-04" });

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("PostPage", () => {
  it("lays out 9 clips over 34.5 s (the shots' durations) with the audio and subtitle tracks", async () => {
    renderPost();
    await ready();
    const picture = within(timeline()).getAllByRole("button", { name: /^画面：/ });
    expect(picture).toHaveLength(9);
    expect(segment("画面：1-04")).toHaveStyle({ left: "28.986%", width: "13.043%" });
    expect(segment("对白：林晚：……周屿？")).toHaveStyle({ left: "31.884%" });
    expect(segment("对白：画外音：三年了。他凭什么。")).toBeInTheDocument();
    expect(segment("环境/音效：雨声（视频原生音频）")).toHaveStyle({ width: "100.000%" });
    expect(segment("环境/音效：门轴声 ×2")).toHaveStyle({ left: "73.913%" });
    expect(segment("音乐：钢琴 · 压低 · 卡点停")).toHaveStyle({ left: "50.725%" });
    expect(within(timeline()).getAllByRole("button", { name: /^字幕：/ })).toHaveLength(2);
    expect(screen.getByTestId("timecode")).toHaveTextContent("00:12 / 00:34");
  });

  it("previews the clip at the playhead: keyframe stand-in and the subtitle", async () => {
    renderPost();
    await ready();
    const preview = screen.getByRole("region", { name: "预览" });
    expect(within(preview).getByText("1-04")).toBeInTheDocument();
    expect(within(preview).getByText("未采纳 · 用关键帧占位")).toBeInTheDocument();
    expect(screen.getByTestId("preview-sub")).toHaveTextContent("……周屿？");
    expect(screen.getByText("还没采纳，暂用关键帧")).toBeInTheDocument();
  });

  it("plays in real time and pauses", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderPost();
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "播放" }));
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByTestId("timecode")).toHaveTextContent("00:15 / 00:34");
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByTestId("timecode")).toHaveTextContent("00:15 / 00:34");
    expect(
      within(screen.getByRole("region", { name: "预览" })).getByText("1-05"),
    ).toBeInTheDocument();
  });

  it("selects a clip and saves its settings", async () => {
    const user = userEvent.setup();
    renderPost();
    await ready();
    await user.click(segment("画面：1-01"));
    expect(screen.getByRole("heading", { name: "片段 1-01" })).toBeInTheDocument();
    expect(screen.getByText("T2 · MiniMax H3 API · 768p")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "换一条候选" })).toHaveAttribute(
      "href",
      "/s/demo/e/1/generate?shot=1-01",
    );
    await user.click(screen.getByRole("switch", { name: "裁掉开头 0.3 秒" }));
    await user.click(screen.getByRole("radio", { name: "叠化 0.3 秒" }));
    const vol = screen.getByRole("slider", { name: "对白音量 80" });
    vol.focus();
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    await waitFor(() =>
      expect(getDb().post.clips["demo-shot-1-01"]).toMatchObject({
        trim_head: false,
        transition: "dissolve",
        dialogue_volume: 78,
      }),
    );
    expect(screen.getByText("对白音量 78")).toBeInTheDocument();
  });

  it("dialogue picks its clip; sfx, music and subtitles open their component", async () => {
    const user = userEvent.setup();
    renderPost();
    await ready();
    await user.click(segment("对白：画外音：三年了。他凭什么。"));
    expect(screen.getByRole("heading", { name: "片段 1-06" })).toBeInTheDocument();
    expect(await screen.findByText("当前产物 · 配乐 · 1 段 · 17 秒")).toBeInTheDocument();
    await user.click(segment("环境/音效：门轴声 ×2"));
    expect(await screen.findByText("当前产物 · 音效 · 3 个")).toBeInTheDocument();
    await user.click(segment(/^字幕：三年了/));
    expect(await screen.findByText("当前产物 · 字幕时间轴 · 2 句")).toBeInTheDocument();
    await user.click(segment("环境/音效：雨声（视频原生音频）"));
    expect(await screen.findByText(/雨声来自视频模型的原生音频/)).toBeInTheDocument();
  });

  it("edits a subtitle: the preview and timeline follow while typing", async () => {
    const user = userEvent.setup();
    renderPost();
    await ready();
    const field = screen.getByRole("textbox", { name: "字幕 00:11 → 00:13" });
    await user.clear(field);
    await user.type(field, "……是你？");
    expect(screen.getByTestId("preview-sub")).toHaveTextContent("……是你？");
    expect(segment("字幕：……是你？")).toBeInTheDocument();
    await user.tab();
    await waitFor(() =>
      expect(getDb().post.subtitles[0]).toMatchObject({ text: "……是你？", edited: true }),
    );
    expect(await screen.findByText("已改，和剧本不同")).toBeInTheDocument();
  });

  it("shows the export checks and starts each export", async () => {
    const user = userEvent.setup();
    renderPost();
    await ready();
    expect(await screen.findByText("还有 6 个镜头没采纳，导出会用关键帧占位")).toBeInTheDocument();
    expect(screen.getByText("响度 -14 LUFS，没有爆音")).toBeInTheDocument();
    await user.click(
      await screen.findByRole("button", { name: "导出成片 MP4 · 9:16 · 1080×1920 · 24 fps" }),
    );
    expect(
      await screen.findByText(/6 个没采纳的镜头会用关键帧占位，并在画面角落标出来/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "导出到达芬奇（FCPXML）" }));
    expect(await screen.findByText(/开始生成 FCPXML/)).toBeInTheDocument();
  });
});
