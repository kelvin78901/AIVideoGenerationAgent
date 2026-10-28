import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ComfySnapshotSchema } from "@/api/schemas/comfy";
import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { WorkflowLibrary } from "@/pages/models/WorkflowLibrary";
import { useUiStore } from "@/stores/ui";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import {
  fakeImport,
  fakeTrialProgress,
  fakeWorkflows,
  finishFakeTrial,
} from "@/test/fakes/workflows";
import { renderAt } from "@/test/render";
import { fakeSetup } from "@/test/setupBackend";

type User = ReturnType<typeof userEvent.setup>;

function Library() {
  useEventStream();
  return <WorkflowLibrary />;
}

const renderLibrary = () =>
  renderAt(
    <>
      <Library />
      <Toaster />
    </>,
    "/models",
  );

const library = () => screen.getByRole("region", { name: "工作流库" });
const row = (name: string) => within(library()).getByRole("rowgroup", { name });
const header = (name: string) => within(row(name)).getAllByRole("row")[0] as HTMLElement;

async function open(user: User, name: string) {
  await screen.findByRole("rowgroup", { name });
  await user.click(screen.getByRole("button", { name: `展开 ${name}` }));
  return row(name);
}

const H3 = "MiniMax H3 图生视频（草稿）";
const FLASHVSR = "FlashVSR 超分（本地 2K 精修兜底）";
const LTX = "雨夜氛围-ltx2";
const SDXL = "sdxl_basic";

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

describe("WorkflowLibrary", () => {
  it("lists workflows by tier with their health check, last trial and file state", async () => {
    const user = userEvent.setup();
    fakeImport("我的/雨夜氛围-ltx2.json");
    fakeImport("sdxl_basic.json");
    renderLibrary();
    await screen.findByRole("rowgroup", { name: LTX });
    expect(within(library()).getAllByRole("rowgroup")).toHaveLength(11);
    expect(header(H3)).toHaveTextContent("comfy/h3视频生成平台推荐正常没试跑过没变");
    expect(header(FLASHVSR)).toHaveTextContent("平台推荐缺 1 个节点包");
    expect(header(LTX)).toHaveTextContent("comfy/ltx2视频生成未验证绑定待确认 8 项没试跑过");

    const tiers = within(library()).getByRole("radiogroup", { name: "按档位筛选" });
    await user.click(within(tiers).getByRole("radio", { name: "未验证 2" }));
    expect(
      within(library())
        .getAllByRole("rowgroup")
        .map((r) => r.getAttribute("aria-label")),
    ).toEqual([LTX, SDXL]);
    await user.click(within(tiers).getByRole("radio", { name: "平台推荐 9" }));
    expect(within(library()).getAllByRole("rowgroup")).toHaveLength(9);
  });

  it("shipped workflows keep the bindings their workflow.yaml names and their tier", async () => {
    const user = userEvent.setup();
    renderLibrary();
    const h3 = await open(user, H3);
    expect(h3).toHaveTextContent("随平台提供 · workflows/h3-i2v/");
    expect(within(h3).getByRole("tab", { name: "试跑", selected: true })).toBeInTheDocument();
    expect(within(h3).queryByRole("button", { name: "升为我的工作流" })).toBeNull();
    expect(within(h3).queryByRole("button", { name: "降为未验证" })).toBeNull();
    await user.click(within(h3).getByRole("tab", { name: "绑定" }));
    expect(h3).toHaveTextContent("随平台提供：绑定写在它的 workflow.yaml 里，这里只看不改。");
    expect(within(h3).queryByRole("combobox")).toBeNull();
    expect(within(h3).queryByRole("button", { name: "确认全部绑定" })).toBeNull();
    expect(within(h3).getAllByText("已确认")).toHaveLength(9);
  });

  it("guessed bindings block the trial and the tier; the trial reports over job events", async () => {
    const user = userEvent.setup();
    fakeImport("sdxl_basic.json");
    renderLibrary();
    const sdxl = await open(user, SDXL);
    expect(within(sdxl).getByRole("tab", { name: "绑定", selected: true })).toBeInTheDocument();
    expect(sdxl).toHaveTextContent("还有 6 项是导入时自动猜的，确认后才能试跑和登记。");
    expect(within(sdxl).getByRole("button", { name: "升为我的工作流" })).toBeDisabled();
    expect(sdxl).toHaveTextContent("先确认绑定");

    // Point the negative prompt at the other text node, then confirm everything.
    await user.selectOptions(
      within(sdxl).getByRole("combobox", { name: "提示词（反向） 的节点" }),
      "Positive",
    );
    await user.click(within(sdxl).getByRole("button", { name: "确认全部绑定" }));
    expect(await screen.findByText("绑定已确认")).toBeInTheDocument();
    await waitFor(() => expect(header(SDXL)).toHaveTextContent("正常"));
    const saved = fakeWorkflows.workflows.find((w) => w.id === "wf_sdxl-basic");
    expect(saved?.bindings.every((b) => b.state === "confirmed")).toBe(true);
    expect(saved?.bindings.find((b) => b.slot === "negative")?.node_title).toBe("Positive");

    // The trial runs on the GPU queue; its steps and its end come as job.updated.
    expect(row(SDXL)).toHaveTextContent("先试跑通过");
    await user.click(within(row(SDXL)).getByRole("tab", { name: "试跑" }));
    await user.click(within(row(SDXL)).getByRole("button", { name: "试跑" }));
    expect(await screen.findByText("已开始试跑：sdxl_basic")).toBeInTheDocument();
    expect(await within(row(SDXL)).findByText("试跑中…（本地 GPU 队列）")).toBeInTheDocument();
    expect(header(SDXL)).toHaveTextContent("试跑中…");
    act(() => fakeTrialProgress("wf_sdxl-basic", 7, 20));
    expect(await within(row(SDXL)).findByText("试跑中… 第 7 / 20 步")).toBeInTheDocument();
    act(() => finishFakeTrial("wf_sdxl-basic"));
    const promote = await within(row(SDXL)).findByRole("button", {
      name: "通过了，升为我的工作流",
    });
    await user.click(promote);
    expect(await screen.findByText("已升为「我的工作流」：sdxl_basic")).toBeVisible();
    await waitFor(() => expect(header(SDXL)).toHaveTextContent("我的工作流"));
  });

  it("missing node packs install after the ComfyUI change list; model files are by hand", async () => {
    const user = userEvent.setup();
    fakeImport("我的/雨夜氛围-ltx2.json");
    renderLibrary();
    const vsr = await open(user, FLASHVSR);
    expect(within(vsr).getByRole("tab", { name: "体检", selected: true })).toBeVisible();
    expect(vsr).toHaveTextContent("节点类 5/6 在");
    const packs = within(vsr).getByRole("table", { name: "缺的节点包" });
    expect(within(packs).getByRole("row", { name: /ComfyUI-FlashVSR/ })).toHaveTextContent(
      "AILab_FlashVSRgit",
    );
    await user.click(within(row(FLASHVSR)).getByRole("tab", { name: "试跑" }));
    expect(within(row(FLASHVSR)).getByRole("button", { name: "试跑" })).toBeDisabled();
    expect(row(FLASHVSR)).toHaveTextContent("先装好缺的节点包和模型");
    await user.click(within(row(FLASHVSR)).getByRole("tab", { name: "体检" }));

    await user.click(within(row(FLASHVSR)).getByRole("button", { name: "安装缺的 1 个节点包" }));
    const dialog = await screen.findByRole("alertdialog", { name: "开始安装前请确认" });
    expect(within(dialog).getByText("会改动你的 ComfyUI（1 项）")).toBeInTheDocument();
    expect(within(dialog).getByRole("row", { name: /^ComfyUI-FlashVSR/ })).toHaveTextContent(
      "安装最新版https://github.com/1038lab/ComfyUI-FlashVSR",
    );
    expect(dialog).toHaveTextContent("装坏了可以在「环境与安装」里一键回滚");
    await user.click(within(dialog).getByRole("button", { name: "确认，开始安装" }));
    expect(
      await screen.findByText("已存快照 2026-10-18_10-05-00_snapshot，装好了 1 个节点包"),
    ).toBeInTheDocument();
    await waitFor(() => expect(header(FLASHVSR)).toHaveTextContent("正常"));
    expect(row(FLASHVSR)).toHaveTextContent("都在：节点类、被绑定的节点标题和字段、模型文件。");

    // A missing checkpoint is listed, but only the node pack goes into the change list.
    await user.click(screen.getByRole("button", { name: `展开 ${LTX}` }));
    await user.click(within(row(LTX)).getByRole("tab", { name: "体检" }));
    expect(row(LTX)).toHaveTextContent("缺的模型文件要自己放进 ComfyUI 的 models 下对应的目录");
    await user.click(within(row(LTX)).getByRole("button", { name: "安装缺的 1 个节点包" }));
    const ltx = await screen.findByRole("alertdialog", { name: "开始安装前请确认" });
    expect(within(ltx).getByText("会改动你的 ComfyUI（1 项）")).toBeInTheDocument();
    expect(within(ltx).getByRole("row", { name: /^ComfyUI-LTXVideo/ })).toBeInTheDocument();
  });

  it("imports from ComfyUI's list; the asset board and imported ones cannot be picked", async () => {
    const user = userEvent.setup();
    fakeImport("sdxl_basic.json");
    renderLibrary();
    await screen.findByRole("rowgroup", { name: SDXL });
    await user.click(screen.getByRole("button", { name: "导入工作流" }));
    const dialog = await screen.findByRole("dialog", { name: "导入工作流" });
    const file = (path: string) => within(dialog).getByRole("listitem", { name: path });
    expect(
      await within(dialog).findByRole("listitem", { name: "DramaStudio 素材板 · 雨停之前.json" }),
    ).toHaveTextContent("素材板，不能登记");
    expect(file("sdxl_basic.json")).toHaveTextContent("已导入");
    expect(within(file("sdxl_basic.json")).queryByRole("button")).toBeNull();
    await user.click(within(file("我的/雨夜氛围-ltx2.json")).getByRole("button", { name: "导入" }));
    expect(await screen.findByText("已导入「雨夜氛围-ltx2」：先确认绑定，再试跑")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const added = await screen.findByRole("rowgroup", { name: LTX });
    expect(added).toHaveTextContent("导入自 我的/雨夜氛围-ltx2.json");
    expect(added).toHaveTextContent("还有 8 项是导入时自动猜的");
    expect(within(added).getByRole("button", { name: `展开 ${LTX}` })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("imports a dropped API-format JSON and refuses other files", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByRole("rowgroup", { name: H3 });
    await user.click(screen.getByRole("button", { name: "导入工作流" }));
    const input = await screen.findByTestId("workflow-file");
    await user.upload(input, new File(['{"nodes": []}'], "ui-format.json"));
    expect(await screen.findByText("这个文件不是 ComfyUI 的 API 格式工作流")).toBeVisible();
    const api = { "3": { class_type: "KSampler", inputs: { seed: 1 } } };
    await user.upload(input, new File([JSON.stringify(api)], "my_flow.json"));
    expect(await screen.findByRole("rowgroup", { name: "my_flow" })).toHaveTextContent(
      "导入自 my_flow.json",
    );
  });

  it("a workflow a node-pack install broke lists why and rolls back to its snapshot", async () => {
    const user = userEvent.setup();
    const sdxl = fakeImport("sdxl_basic.json");
    const snap = ComfySnapshotSchema.parse({
      id: "snap-grain",
      manager_name: "2026-10-28_17-40-00_snapshot",
      env_hash: null,
      reason: "install",
      changes: [],
      created_at: "2026-10-28T09:40:00Z",
      restore: null,
      restored_at: null,
    });
    fakeSetup.snapshots.unshift(snap);
    sdxl.bindings = sdxl.bindings.map((b) => ({ ...b, state: "confirmed" }));
    if (!sdxl.check) throw new Error("sdxl_basic is checked in the export");
    sdxl.check = {
      ...sdxl.check,
      status: "broken",
      problems: [
        { code: "unknown_node", params: { class: "KSampler" } },
        {
          code: "broke_after_install",
          params: { snapshot: snap.manager_name, snapshot_id: snap.id },
        },
      ],
    };
    renderLibrary();
    await screen.findByRole("rowgroup", { name: SDXL });
    expect(header(SDXL)).toHaveTextContent("有问题 2 处");
    const r = await open(user, SDXL);
    await user.click(within(r).getByRole("tab", { name: "体检" }));
    const problems = within(row(SDXL)).getByRole("list", { name: "问题" });
    expect(problems).toHaveTextContent("节点类 KSampler 在 ComfyUI 里找不到，也没有节点包提供它");
    expect(problems).toHaveTextContent(
      "上次装节点包之前是好的，装完坏了（安装前存了快照 2026-10-28_17-40-00_snapshot）",
    );

    await user.click(within(row(SDXL)).getByRole("button", { name: "回滚到这次安装前的快照" }));
    const ask = within(row(SDXL)).getByRole("group", { name: "回滚到这次安装前的快照" });
    expect(ask).toHaveTextContent("ComfyUI-Manager 在 ComfyUI 下次启动时执行");
    await user.click(within(ask).getByRole("button", { name: "确认回滚" }));
    expect(
      await screen.findByText(/已排上回滚到 2026-10-28_17-40-00_snapshot/),
    ).toBeInTheDocument();
    expect(fakeSetup.snapshots[0]?.restore?.state).toBe("pending");
  });

  it("my workflows can go back to unverified", async () => {
    const user = userEvent.setup();
    const w = fakeImport("sdxl_basic.json");
    w.tier = "mine";
    w.bindings = w.bindings.map((b) => ({ ...b, state: "confirmed" }));
    renderLibrary();
    const sdxl = await open(user, SDXL);
    await user.click(within(sdxl).getByRole("button", { name: "降为未验证" }));
    expect(await screen.findByText("已降为未验证：sdxl_basic")).toBeVisible();
    await waitFor(() => expect(header(SDXL)).toHaveTextContent("未验证"));
  });

  it("switches to English", async () => {
    fakeImport("我的/雨夜氛围-ltx2.json");
    act(() => useUiStore.getState().toggleLang());
    try {
      renderLibrary();
      expect(await screen.findByRole("region", { name: "Workflow library" })).toBeInTheDocument();
      const ltx = await screen.findByRole("rowgroup", { name: LTX });
      expect(screen.getByRole("radio", { name: "Unverified 1" })).toBeInTheDocument();
      expect(ltx).toHaveTextContent("Unverified8 bindings to confirmNever run");
    } finally {
      act(() => useUiStore.getState().toggleLang());
    }
  });
});
