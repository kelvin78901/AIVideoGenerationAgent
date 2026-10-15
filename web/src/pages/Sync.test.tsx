import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import SyncPage from "@/pages/Sync";
import { useUiStore } from "@/stores/ui";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

function Page() {
  useEventStream();
  return (
    <>
      <SyncPage />
      <Toaster />
    </>
  );
}

const renderSync = () =>
  renderAt(
    <Routes>
      <Route path="/s/:series/sync" element={<Page />} />
    </Routes>,
    "/s/demo/sync",
  );

const card = (name: string) => screen.getByRole("region", { name });
const target = (id: string) => getDb().sync.targets.find((x) => x.id === id);
const ready = () => screen.findByRole("region", { name: "达芬奇 Resolve" });
const timing = { ...demoTiming };

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  demoTiming.syncTickMs = 0; // all 24 files in one task (mocks/events.ts:repeatDemo)
});
afterEach(() => {
  vi.unstubAllGlobals();
  Object.assign(demoTiming, timing);
});

describe("SyncPage", () => {
  it("shows the four targets, the board with 1-03 picked, rules and the log", async () => {
    renderSync();
    await ready();
    expect(within(card("ComfyUI 画布")).getByText("双向")).toBeInTheDocument();
    expect(card("ComfyUI 画布")).toHaveTextContent(
      "已连接 127.0.0.1:8188 · 节点包 DramaStudio 已装",
    );
    expect(card("ComfyUI 画布")).toHaveTextContent("（短剧 / 雨停之前）");
    expect(within(card("Eagle 素材库")).getByRole("switch")).not.toBeChecked();
    expect(
      within(card("达芬奇 Resolve")).getByRole("radio", { name: "文件夹 + FCPXML（免费版）" }),
    ).toBeChecked();

    const board = await screen.findByRole("group", { name: "素材板节点" });
    expect(within(board).getByRole("button", { name: "1-03，已采纳 v2" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(board).getByText("1080×1920 · 24fps")).toBeInTheDocument();
    expect(within(board).getByText("场 1 · 老小区楼道（5 镜）")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("质检 画面文字逐字一致");

    expect(screen.getByRole("radio", { name: "采纳或锁定时（推荐）" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "视频（全部候选）" })).not.toBeChecked();
    const log = await screen.findByRole("list", { name: "同步记录" });
    expect(within(log).getAllByRole("listitem")).toHaveLength(6);
    expect(log).toHaveTextContent("→ ComfyUI 素材板 · 本地文件夹 · Eagle 没检测到，已跳过");
  });

  it("Eagle cannot be turned on until detected; Resolve free cannot create bins", async () => {
    const user = userEvent.setup();
    renderSync();
    await ready();
    await user.click(within(card("Eagle 素材库")).getByRole("switch"));
    expect(
      await screen.findByText("没检测到 Eagle 素材库：请先安装并打开，再点「重新检测」。"),
    ).toBeInTheDocument();
    expect(target("eagle")?.enabled).toBe(false);
    await user.click(within(card("Eagle 素材库")).getByRole("button", { name: "重新检测" }));
    await waitFor(() =>
      expect(card("Eagle 素材库")).toHaveTextContent(
        "还是没检测到 Eagle（默认端口 41595 没有响应）",
      ),
    );

    await user.click(
      within(card("达芬奇 Resolve")).getByRole("radio", { name: "自动建 Bin（需要 Studio）" }),
    );
    expect(await screen.findByText(/自动建 Bin 需要 Studio 版/)).toBeInTheDocument();
    expect(target("resolve")?.mode).toBe("fcpxml");

    await user.click(within(card("本地文件夹")).getByRole("switch"));
    await waitFor(() => expect(target("folder")?.enabled).toBe(false));
    expect(
      within(card("本地文件夹")).getByRole("switch", { name: "本地文件夹：未开启同步" }),
    ).not.toBeChecked();
  });

  it("picking a node shows its file and version", async () => {
    const user = userEvent.setup();
    renderSync();
    const board = await screen.findByRole("group", { name: "素材板节点" });
    await user.click(within(board).getByRole("button", { name: "1-04，待挑选 · 4 条" }));
    expect(screen.getByRole("status")).toHaveTextContent("状态 还没采纳，最好的 T3 人脸 0.82");
    await user.click(within(board).getByRole("button", { name: "DramaStudio ▸ 存回工作台" }));
    expect(screen.getByRole("status")).toHaveTextContent("不会 覆盖已采纳的版本");
  });

  it("rules save as they change; the layout example follows", async () => {
    const user = userEvent.setup();
    renderSync();
    await ready();
    await user.click(screen.getByRole("radio", { name: "每次生成都同步" }));
    await waitFor(() => expect(getDb().sync.rules.when).toBe("every"));
    await user.click(screen.getByRole("checkbox", { name: "角色" }));
    await user.click(screen.getByRole("checkbox", { name: "视频（全部候选）" }));
    await waitFor(() => expect(getDb().sync.rules.kinds).toContain("video_all"));
    expect(getDb().sync.rules.kinds).not.toContain("character");
    expect(screen.getByText("D:\\短剧\\雨停之前\\E01\\S01\\1-03\\")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "按素材类型" }));
    expect(await screen.findByText("D:\\短剧\\雨停之前\\E01\\视频\\")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "质检分" }));
    await waitFor(() => expect(getDb().sync.rules.extras).toEqual(["prompt", "model_cost"]));
  });

  it("sync now shows progress, then a toast and a new log line", async () => {
    const user = userEvent.setup();
    renderSync();
    await ready();
    await user.click(screen.getByRole("button", { name: "立即同步" }));
    expect(
      await screen.findByText("同步完成：检查了 24 个文件，新增 3 个，其余没有变化。"),
    ).toBeInTheDocument();
    const log = screen.getByRole("list", { name: "同步记录" });
    await waitFor(() => expect(within(log).getAllByRole("listitem")).toHaveLength(7));
    expect(within(log).getAllByRole("listitem")[0]).toHaveTextContent(
      "手动同步：24 个文件，其中新增 3 个→ ComfyUI 素材板 · 本地文件夹 · 达芬奇文件夹",
    );
    expect(screen.getByRole("button", { name: "立即同步" })).toBeEnabled();
  });

  it("switches to English", async () => {
    act(() => useUiStore.getState().toggleLang());
    try {
      renderSync();
      expect(
        await screen.findByRole("heading", { level: 1, name: "Asset sync" }),
      ).toBeInTheDocument();
      expect(await screen.findByRole("region", { name: "DaVinci Resolve" })).toHaveTextContent(
        "Free edition 21.1 found: no external scripting",
      );
      const board = await screen.findByRole("group", { name: "Board nodes" });
      expect(within(board).getByText("Scene 1 · 老小区楼道 (5 shots)")).toBeInTheDocument();
    } finally {
      act(() => useUiStore.getState().toggleLang());
    }
  });
});
