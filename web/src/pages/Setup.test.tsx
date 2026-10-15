import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import SetupPage from "@/pages/Setup";
import { useUiStore } from "@/stores/ui";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

function Page() {
  useEventStream();
  return (
    <>
      <SetupPage />
      <Toaster />
    </>
  );
}

const renderSetup = () => renderAt(<Page />, "/setup");
const row = (name: string) => screen.getByRole("listitem", { name });
const summary = () => screen.getByRole("region", { name: "检测结果" });
const timing = { ...demoTiming };
/** Scan and install run on timers; the full suite runs files in parallel, so allow time. */
const WAIT = { timeout: 8000 };

async function scan(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "开始检测" }));
  await waitFor(
    () => expect(within(summary()).getByRole("status")).toHaveTextContent("检测完成"),
    WAIT,
  );
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  demoTiming.setupScanMs = 2;
  demoTiming.setupTickMs = 2;
});
afterEach(() => {
  vi.unstubAllGlobals();
  Object.assign(demoTiming, timing);
});

describe("SetupPage", { timeout: 30_000 }, () => {
  it("starts before the first scan: what will be checked, step 1, the PC sample machine", async () => {
    renderSetup();
    expect(await screen.findByRole("heading", { name: "会检测这些" })).toBeInTheDocument();
    expect(screen.getByText("Python、PyTorch 的 CUDA 版本、FFmpeg、Git")).toBeInTheDocument();
    expect(screen.getByText("只读取信息，不会改动任何东西，大约 10 秒。")).toBeInTheDocument();
    const steps = screen.getByRole("list", { name: "安装步骤" });
    expect(within(steps).getByText("检测主机").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    const machine = screen.getByRole("radiogroup", { name: "示例机器（原型演示用）" });
    expect(within(machine).getByRole("radio", { name: "Windows + RTX 5090" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("scans item by item, then ticks what is required", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    expect(within(summary()).getByText("通过 8")).toBeInTheDocument();
    expect(within(summary()).getByText("缺少 8")).toBeInTheDocument();
    expect(within(summary()).getByText("需更新 2")).toBeInTheDocument();
    expect(within(summary()).getByText("可选 6")).toBeInTheDocument();
    expect(within(summary()).getByText("注意 1")).toBeInTheDocument();
    expect(row("PyTorch")).toHaveTextContent("已装，但不是 CUDA 13 版");
    expect(row("PyTorch")).toHaveTextContent("换成 CUDA 13.0 版（NVFP4 量化需要）");
    expect(row("显卡")).toHaveTextContent("NVIDIA RTX 5090 · 32 GB 显存");
    expect(row("磁盘空间")).toHaveTextContent("D: 剩余 1.2 TB");
    expect(screen.getByRole("checkbox", { name: "安装 FFmpeg" })).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "安装（可选） SageAttention 加速" }),
    ).not.toBeChecked();
    expect(screen.getByRole("button", { name: "安装选中的 10 项" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "全选" }));
    expect(screen.getByRole("button", { name: "安装选中的 15 项" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "安装（可选） Fun ControlNet 节点" }));
    expect(screen.getByRole("button", { name: "安装选中的 14 项" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "只选必需的" }));
    expect(screen.getByRole("button", { name: "安装选中的 10 项" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "先跳过，进入工作台" })).toHaveAttribute(
      "href",
      "/s/demo/e/1/novel",
    );
  });

  it("mirror and location go with the install request", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    const mirror = screen.getByRole("radiogroup", { name: "下载源" });
    expect(screen.getByText(/先测速，哪个快用哪个/)).toBeInTheDocument();
    await user.click(within(mirror).getByRole("radio", { name: "国内镜像" }));
    expect(screen.getByText(/用国内镜像下载 Python 包和模型权重/)).toBeInTheDocument();
    const dir = screen.getByLabelText("安装位置");
    await user.clear(dir);
    await user.type(dir, "E:\\Studio");
    await user.click(screen.getByRole("button", { name: "安装选中的 10 项" }));
    expect(getDb().profile.install).toMatchObject({ mirror: "cn", dir: "E:\\Studio" });
    expect(await screen.findByText("下载源：国内镜像 · E:\\Studio")).toBeInTheDocument();
  });

  it("installs in order; SageAttention fails and can be retried or skipped", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    await user.click(screen.getByRole("button", { name: "全选" }));
    await user.click(screen.getByRole("button", { name: "安装选中的 15 项" }));
    expect(await screen.findByRole("heading", { name: "安装日志" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "准备好了" }, WAIT)).toBeInTheDocument();

    expect(screen.getByText("装好 14 项，失败 1 项（都是可选项）。")).toBeInTheDocument();
    expect(screen.getByText("均衡：草稿和重跑在本地跑，采纳前用 API 出终版")).toBeInTheDocument();
    expect(screen.getByText("开始：FFmpeg")).toBeInTheDocument();
    expect(screen.getByText("失败（可选项，不影响使用）：SageAttention 加速")).toBeInTheDocument();
    expect(screen.getByText("全部结束。")).toBeInTheDocument();
    expect(within(summary()).getByText("已装好 14")).toBeInTheDocument();
    expect(within(summary()).getByText("失败 1")).toBeInTheDocument();
    const sage = row("SageAttention 加速");
    expect(sage).toHaveTextContent("没有适合这台机器的预编译包");
    expect(within(sage).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");
    expect(row("FFmpeg")).toHaveTextContent("已装好");
    const steps = screen.getByRole("list", { name: "安装步骤" });
    expect(within(steps).getByText("完成").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("link", { name: "新建剧集：先定画幅和规格" })).toHaveAttribute(
      "href",
      "/s/demo/spec",
    );

    await user.click(within(sage).getByRole("button", { name: "重试 SageAttention 加速" }));
    expect(await screen.findByText("重试：SageAttention 加速")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("全部结束。")).toHaveLength(2), WAIT);
    await user.click(
      within(row("SageAttention 加速")).getByRole("button", { name: "跳过 SageAttention 加速" }),
    );
    await waitFor(() => expect(row("SageAttention 加速")).toHaveTextContent(/^跳过/));
    expect(screen.getByText("已跳过：SageAttention 加速")).toBeInTheDocument();
  });

  it("the Mac sample machine: CUDA-only items skipped, video via API", async () => {
    const user = userEvent.setup();
    renderSetup();
    const machine = await screen.findByRole("radiogroup", { name: "示例机器（原型演示用）" });
    await user.click(within(machine).getByRole("radio", { name: "Mac M4 Pro" }));
    await scan(user);
    expect(row("MiniMax H3 节点")).toHaveTextContent("需要 CUDA");
    expect(row("MiniMax H3 节点")).toHaveTextContent("不支持，跳过");
    expect(row("显卡")).toHaveTextContent("不支持 CUDA：视频生成改走 API");
    expect(screen.getByRole("button", { name: "安装选中的 4 项" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "安装选中的 4 项" }));
    expect(await screen.findByText("均衡（视频走 API）", {}, WAIT)).toBeInTheDocument();
    expect(screen.getByText("装好 4 项。")).toBeInTheDocument();
  });

  it("a rescan after installing reports what is now installed", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    await user.click(screen.getByRole("button", { name: "安装选中的 10 项" }));
    await screen.findByRole("heading", { name: "准备好了" }, WAIT);
    await user.click(screen.getByRole("button", { name: "重新检测" }));
    await waitFor(
      () => expect(within(summary()).getByRole("status")).toHaveTextContent("检测完成"),
      WAIT,
    );
    expect(row("FFmpeg")).toHaveTextContent(/^通过/);
    expect(within(summary()).getByText("通过 18")).toBeInTheDocument();
  });

  it("switches to English, item names included", async () => {
    const user = userEvent.setup();
    act(() => useUiStore.getState().toggleLang());
    try {
      renderSetup();
      await user.click(await screen.findByRole("button", { name: "Start scan" }));
      await screen.findByText("Scan complete");
      expect(screen.getByRole("listitem", { name: "Operating system" })).toHaveTextContent(
        "Windows 11 · 64-bit",
      );
      expect(screen.getByRole("listitem", { name: "Model download network" })).toHaveTextContent(
        "Pick China mirror or Automatic below",
      );
      expect(screen.getByRole("button", { name: "Install 10 selected" })).toBeInTheDocument();
    } finally {
      act(() => useUiStore.getState().toggleLang());
    }
  });
});
