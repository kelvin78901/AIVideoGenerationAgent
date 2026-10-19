import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import SetupPage from "@/pages/Setup";
import { useUiStore } from "@/stores/ui";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";
import { fakeSetup } from "@/test/setupBackend";

function Page() {
  useEventStream();
  return (
    <>
      <SetupPage />
      <Toaster />
    </>
  );
}

type User = ReturnType<typeof userEvent.setup>;

const renderSetup = () => renderAt(<Page />, "/setup");
const row = (name: string) => screen.getByRole("listitem", { name });
const summary = () => screen.getByRole("region", { name: "检测结果" });
const phaseIs = (text: string) =>
  waitFor(() => expect(within(summary()).getByRole("status")).toHaveTextContent(text));

async function scan(user: User) {
  await user.click(await screen.findByRole("button", { name: "开始检测" }));
  await phaseIs("检测完成");
}

/** Ticks everything, installs, approves the ComfyUI changes and waits for the end. */
async function installAll(user: User) {
  await user.click(screen.getByRole("button", { name: "全选" }));
  await user.click(screen.getByRole("button", { name: "安装选中的 11 项" }));
  const dialog = await screen.findByRole("alertdialog", { name: "开始安装前请确认" });
  await user.click(within(dialog).getByRole("button", { name: "确认，开始安装" }));
  await screen.findByRole("heading", { name: "准备好了" });
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

describe("SetupPage", () => {
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
    expect(screen.queryByRole("heading", { name: "你的 ComfyUI" })).not.toBeInTheDocument();
  });

  it("shows the sample machine switch only for Mock's sample machines", async () => {
    fakeSetup.profile.simulated = false;
    renderSetup();
    await screen.findByRole("heading", { name: "会检测这些" });
    expect(screen.queryByRole("radiogroup", { name: "示例机器（原型演示用）" })).toBeNull();
  });

  it("scans, then ticks what is required except changes to the user's ComfyUI", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    expect(within(summary()).getByText("通过 10")).toBeInTheDocument();
    expect(within(summary()).getByText("缺少 9")).toBeInTheDocument();
    expect(within(summary()).getByText("需更新 2")).toBeInTheDocument();
    expect(within(summary()).getByText("可选 8")).toBeInTheDocument();
    expect(within(summary()).getByText("注意 1")).toBeInTheDocument();
    expect(row("PyTorch")).toHaveTextContent("已装，但不是 CUDA 13 版");
    expect(row("显卡")).toHaveTextContent("NVIDIA RTX 5090 · 32 GB 显存");
    expect(row("磁盘空间")).toHaveTextContent("D: 剩余 1.2 TB");
    expect(row("ComfyUI-Manager（快照和回滚）")).toHaveTextContent("4.2.2");

    expect(screen.getByRole("checkbox", { name: "安装 FFmpeg" })).toBeChecked();
    expect(row("ComfyUI")).toHaveTextContent("会改动你的 ComfyUI");
    expect(screen.getByRole("checkbox", { name: "安装 ComfyUI" })).not.toBeChecked();
    expect(row("FFmpeg")).not.toHaveTextContent("会改动你的 ComfyUI");
    // H3 and SeedVR2 come with ComfyUI, our own nodes are not out yet: nothing to tick.
    expect(row("MiniMax H3 节点")).toHaveTextContent(
      "ComfyUI 自带：把 ComfyUI 更新到 0.30.0 或更新",
    );
    expect(within(row("MiniMax H3 节点")).queryByRole("checkbox")).toBeNull();
    expect(row("SeedVR2 节点（本地超分）")).toHaveTextContent("更新到 0.28.0 或更新");
    expect(within(row("SeedVR2 节点（本地超分）")).queryByRole("checkbox")).toBeNull();
    expect(row("DramaStudio 节点包（素材板与存回）")).toHaveTextContent(
      "还没发布：随 ComfyUI 对接一起提供",
    );
    expect(within(row("DramaStudio 节点包（素材板与存回）")).queryByRole("checkbox")).toBeNull();
    // Weights for ComfyUI go into its model folders: offered, not ticked. IndexTTS is ticked.
    expect(row("MiniMax H3 权重（int8）")).toHaveTextContent("会改动你的 ComfyUI");
    expect(
      screen.getByRole("checkbox", { name: "安装 MiniMax H3 权重（int8）" }),
    ).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "安装 IndexTTS-2.5" })).toBeChecked();
    expect(screen.getByRole("button", { name: "安装选中的 2 项" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "全选" }));
    expect(screen.getByRole("button", { name: "安装选中的 11 项" })).toBeInTheDocument();
    await user.click(
      screen.getByRole("checkbox", { name: "安装（可选） FlashVSR 节点（快速超分）" }),
    );
    expect(screen.getByRole("button", { name: "安装选中的 10 项" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "只选必需的" }));
    expect(screen.getByRole("button", { name: "安装选中的 2 项" })).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "安装选中的 2 项" }));
    expect(fakeSetup.profile.install).toMatchObject({ mirror: "cn", dir: "E:\\Studio" });
    expect(await screen.findByText("下载源：国内镜像 · E:\\Studio")).toBeInTheDocument();
  });

  it("installs what leaves ComfyUI alone without asking", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    await user.click(screen.getByRole("button", { name: "安装选中的 2 项" }));
    expect(await screen.findByRole("heading", { name: "准备好了" })).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).toBeNull(); // IndexTTS-2.5 is 5.5 GB
    expect(screen.getByText("装好 2 项。")).toBeInTheDocument();
    expect(screen.getByText("开始：FFmpeg")).toBeInTheDocument();
    expect(screen.getByText("开始：IndexTTS-2.5")).toBeInTheDocument();
    expect(screen.queryByText(/已存 ComfyUI 快照/)).toBeNull();
    expect(screen.getByText("还没有快照。装或升级会改动 ComfyUI 的项之前，会自动存一份。"));
  });

  it("lists every change to the user's ComfyUI first; cancel installs nothing", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    await user.click(screen.getByRole("button", { name: "全选" }));
    await user.click(screen.getByRole("button", { name: "安装选中的 11 项" }));
    const dialog = await screen.findByRole("alertdialog", { name: "开始安装前请确认" });
    expect(within(dialog).getByText("会改动你的 ComfyUI（8 项）")).toBeInTheDocument();
    expect(within(dialog).getByText("D:\\ComfyUI")).toBeInTheDocument();
    const change = (name: string) => within(dialog).getByRole("cell", { name }).closest("tr");
    expect(change("PyTorch")).toHaveTextContent(
      "升级2.7.1+cu128 → 最新版torch torchvision torchaudio",
    );
    expect(change("ComfyUI")).toHaveTextContent(
      "升级0.3.40 → v0.42.1https://github.com/comfyanonymous/ComfyUI",
    );
    // No tag upstream: the pinned commit, short; weights: the pinned Hugging Face revision.
    expect(change("FlashVSR 节点（快速超分）")).toHaveTextContent(
      "安装8877fddhttps://github.com/1038lab/ComfyUI-FlashVSR",
    );
    expect(change("MiniMax H3 权重（int8）")).toHaveTextContent(
      "安装e5eb578Comfy-Org/MiniMax-H3约 49.3 GB",
    );
    expect(within(dialog).getAllByRole("row")).toHaveLength(9);
    expect(
      within(dialog).getByText("MiniMax H3 权重（int8） 要下载约 49.3 GB"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/动手前先用 ComfyUI-Manager 存一份快照/)).toBeInTheDocument();
    expect(await screen.findByText("等你确认后开始安装")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "取消" }));
    await phaseIs("检测完成");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    // Back at the scan result, the selection kept.
    expect(screen.getByRole("button", { name: "安装选中的 11 项" })).toBeEnabled();
    expect(fakeSetup.profile.items.every((x) => x.install === null)).toBe(true);
    expect(fakeSetup.installed.size).toBe(0);
    expect(fakeSetup.snapshots).toHaveLength(0);
  });

  it("approved: snapshot first, SageAttention fails and can be retried or skipped", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    await installAll(user);

    expect(screen.getByText("装好 10 项，失败 1 项（都是可选项）。")).toBeInTheDocument();
    expect(screen.getByText("均衡：草稿和重跑在本地跑，采纳前用 API 出终版")).toBeInTheDocument();
    const lines = within(screen.getByRole("region", { name: "安装日志" })).getAllByRole("listitem");
    const text = lines.map((l) => l.textContent);
    const snapshotAt = text.findIndex((l) => l?.startsWith("已存 ComfyUI 快照："));
    expect(snapshotAt).toBeGreaterThan(text.indexOf("开始：PyTorch"));
    expect(snapshotAt).toBeLessThan(text.indexOf("完成：PyTorch"));
    expect(text).toContain("失败（可选项，不影响使用）：SageAttention 加速");
    expect(text.at(-1)).toBe("全部结束。");
    expect(within(summary()).getByText("已装好 10")).toBeInTheDocument();
    expect(within(summary()).getByText("失败 1")).toBeInTheDocument();
    const sage = row("SageAttention 加速");
    expect(sage).toHaveTextContent("没有适合这台机器的预编译包");
    expect(within(sage).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");
    const steps = screen.getByRole("list", { name: "安装步骤" });
    expect(within(steps).getByText("完成").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("link", { name: "新建剧集：先定画幅和规格" })).toHaveAttribute(
      "href",
      "/s/demo/spec",
    );

    const snapshots = await screen.findByRole("list", { name: "快照" });
    const snap = within(snapshots).getByRole("listitem");
    expect(snap).toHaveTextContent("安装前");
    expect(snap).toHaveTextContent("为这些改动存的：PyTorch、ComfyUI、FlashVSR 节点（快速超分）");

    await user.click(within(sage).getByRole("button", { name: "重试 SageAttention 加速" }));
    expect(await screen.findByText("重试：SageAttention 加速")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("全部结束。")).toHaveLength(2));
    await user.click(
      within(row("SageAttention 加速")).getByRole("button", { name: "跳过 SageAttention 加速" }),
    );
    await waitFor(() => expect(row("SageAttention 加速")).toHaveTextContent(/^跳过/));
    expect(screen.getByText("已跳过：SageAttention 加速")).toBeInTheDocument();
    expect(fakeSetup.snapshots).toHaveLength(1);
  });

  it("shows the user's ComfyUI as identified, with its node packs and model files", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    const panel = await screen.findByRole("region", { name: "你的 ComfyUI" });
    expect(panel).toHaveTextContent("D:\\ComfyUI · 文件夹安装");
    expect(panel).toHaveTextContent("http://127.0.0.1:8188");
    expect(panel).toHaveTextContent("ComfyUI 0.3.40 · Python 3.12.9 · PyTorch 2.7.1+cu128");
    expect(panel).toHaveTextContent("ComfyUI-Manager4.2.2");
    await user.click(within(panel).getByRole("button", { name: "节点包 3 个 · 模型文件 3 个" }));
    const packs = within(panel).getByRole("table", { name: "节点包" });
    expect(within(packs).getByRole("row", { name: /ComfyUI-VideoHelperSuite/ })).toHaveTextContent(
      "git1.7.9",
    );
    expect(within(packs).getByRole("row", { name: /ComfyUI-KJNodes/ })).toHaveTextContent(
      "Registry1.2.6",
    );
    const models = within(panel).getByRole("table", { name: "模型文件" });
    expect(within(models).getByRole("row", { name: /sd_xl_base/ })).toHaveTextContent(
      "checkpoints6.5 GB",
    );
    expect(within(models).getByRole("row", { name: /rain_style/ })).toHaveTextContent("218 MB");
  });

  it("takes a snapshot on request and rolls back after asking", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    const panel = await screen.findByRole("region", { name: "你的 ComfyUI" });
    await user.click(within(panel).getByRole("button", { name: "现在存一份" }));
    expect(await screen.findByText(/^已存快照：/)).toBeInTheDocument();
    const snap = await within(panel).findByRole("listitem");
    expect(snap).toHaveTextContent("手动");

    await user.click(within(snap).getByRole("button", { name: /^回滚到 .* 的快照$/ }));
    const ask = await screen.findByRole("alertdialog", { name: /^回滚到 .* 的快照？$/ });
    expect(ask).toHaveTextContent("平台不会替你重启 ComfyUI");
    await user.click(within(ask).getByRole("button", { name: "取消" }));
    expect(fakeSetup.snapshots[0]?.restored_at).toBeNull();

    await user.click(within(snap).getByRole("button", { name: /^回滚到 .* 的快照$/ }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "回滚" }),
    );
    expect(await screen.findByText("已安排回滚：重启 ComfyUI 后生效")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(panel).getByRole("listitem")).toHaveTextContent(
        "已安排回滚，重启 ComfyUI 后生效",
      ),
    );
  });

  it("leaves ComfyUI alone when no snapshot can be taken", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    fakeSetup.snapshotFail = "not_running";
    await user.click(screen.getByRole("button", { name: "只选必需的" }));
    await user.click(screen.getByRole("checkbox", { name: "安装 ComfyUI" }));
    await user.click(screen.getByRole("button", { name: "安装选中的 3 项" }));
    const dialog = await screen.findByRole("alertdialog", { name: "开始安装前请确认" });
    expect(within(dialog).getByText("会改动你的 ComfyUI（1 项）")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "确认，开始安装" }));
    await screen.findByRole("heading", { name: "准备好了" });

    const notRunning = "ComfyUI 没在运行，存不了快照，所以没有动它。打开 ComfyUI 后重试";
    expect(row("ComfyUI")).toHaveTextContent(notRunning);
    expect(row("FFmpeg")).toHaveTextContent("已装好");
    expect(
      screen.getByText("存不了 ComfyUI 快照，会改动 ComfyUI 的项这次不装"),
    ).toBeInTheDocument();
    const panel = screen.getByRole("region", { name: "你的 ComfyUI" });
    expect(within(panel).getByRole("alert")).toHaveTextContent(notRunning);
    await user.click(within(panel).getByRole("button", { name: "现在存一份" }));
    expect(await screen.findByText("ComfyUI 没在运行，打开它后重试")).toBeInTheDocument();
  });

  it("the Mac sample machine: CUDA-only items skipped, no ComfyUI of its own, video via API", async () => {
    const user = userEvent.setup();
    renderSetup();
    const machine = await screen.findByRole("radiogroup", { name: "示例机器（原型演示用）" });
    await user.click(within(machine).getByRole("radio", { name: "Mac M4 Pro" }));
    await scan(user);
    expect(row("MiniMax H3 节点")).toHaveTextContent("需要 CUDA");
    expect(row("MiniMax H3 节点")).toHaveTextContent("不支持，跳过");
    expect(row("显卡")).toHaveTextContent("不支持 CUDA：视频生成改走 API");
    expect(row("ComfyUI")).not.toHaveTextContent("会改动你的 ComfyUI");
    expect(screen.queryByRole("region", { name: "你的 ComfyUI" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "安装选中的 3 项" }));
    expect(await screen.findByText("均衡（视频走 API）")).toBeInTheDocument();
    expect(screen.getByText("装好 3 项。")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("a rescan after installing reports what is now installed", async () => {
    const user = userEvent.setup();
    renderSetup();
    await scan(user);
    await user.click(screen.getByRole("button", { name: "安装选中的 2 项" }));
    await screen.findByRole("heading", { name: "准备好了" });
    await user.click(screen.getByRole("button", { name: "重新检测" }));
    await phaseIs("检测完成");
    expect(row("FFmpeg")).toHaveTextContent(/^通过/);
    expect(row("IndexTTS-2.5")).toHaveTextContent(/^通过/);
    expect(within(summary()).getByText("通过 12")).toBeInTheDocument();
  });

  it("switches to English, item names and the change list included", async () => {
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
      expect(screen.getByRole("button", { name: "Install 2 selected" })).toBeInTheDocument();
      await user.click(screen.getByRole("checkbox", { name: "Install ComfyUI" }));
      await user.click(screen.getByRole("button", { name: "Install 3 selected" }));
      const dialog = await screen.findByRole("alertdialog", { name: "Confirm before installing" });
      expect(within(dialog).getByText("Changes to your ComfyUI (1)")).toBeInTheDocument();
      expect(within(dialog).getByRole("row", { name: /ComfyUI Update/ })).toHaveTextContent(
        "0.3.40 → v0.42.1",
      );
    } finally {
      act(() => useUiStore.getState().toggleLang());
    }
  });
});
