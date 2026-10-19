import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Toaster } from "@/components/ui/sonner";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { WorkflowLibrary } from "@/pages/models/WorkflowLibrary";
import { useUiStore } from "@/stores/ui";
import { backend } from "@/test/backend";
import { renderAt } from "@/test/render";

type User = ReturnType<typeof userEvent.setup>;

const renderLibrary = () =>
  renderAt(
    <>
      <WorkflowLibrary />
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

const WAN = "Wan 2.2 图生视频（社区）";
const KONTEXT = "Flux Kontext 关键帧（社区）";
const timing = { ...demoTiming };

beforeEach(() => {
  backend();
  demoTiming.workflowTrialMs = 20;
});
afterEach(() => Object.assign(demoTiming, timing));

describe("WorkflowLibrary", () => {
  it("lists workflows by tier with their health check, last trial and file state", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByRole("rowgroup", { name: WAN });
    expect(within(library()).getAllByRole("rowgroup")).toHaveLength(5);
    expect(header("MiniMax H3 · 视频草稿")).toHaveTextContent(
      "comfy/h3-draft视频生成平台推荐正常10-17 21:40 通过 · 52 秒没变",
    );
    expect(header("LatentSync 口型")).toHaveTextContent("口型修复我的工作流正常");
    expect(header(WAN)).toHaveTextContent("未验证绑定待确认 3 项没试跑过");
    expect(header(KONTEXT)).toHaveTextContent("缺 2 个节点包、1 个模型");

    const tiers = within(library()).getByRole("radiogroup", { name: "按档位筛选" });
    await user.click(within(tiers).getByRole("radio", { name: "未验证 2" }));
    expect(
      within(library())
        .getAllByRole("rowgroup")
        .map((r) => r.getAttribute("aria-label")),
    ).toEqual([WAN, KONTEXT]);
    await user.click(within(tiers).getByRole("radio", { name: "平台推荐 2" }));
    expect(within(library()).getAllByRole("rowgroup")).toHaveLength(2);
  });

  it("recommended workflows use DramaStudio nodes: nothing to bind, no tier to change", async () => {
    const user = userEvent.setup();
    renderLibrary();
    const h3 = await open(user, "MiniMax H3 · 视频草稿");
    expect(h3).toHaveTextContent("随平台提供 · workflows/h3-draft/");
    expect(h3).toHaveTextContent("能力：画幅 9:16 16:9 3:4 1:1 21:9 · 最长 10 秒 · 参考图 1 张");
    expect(within(h3).getByRole("tab", { name: "试跑", selected: true })).toBeInTheDocument();
    expect(h3).toHaveTextContent("通过 · 2026-10-17 21:40 · 用时 52 秒 · 显存 22.4 GB");
    expect(within(h3).queryByRole("button", { name: "升为我的工作流" })).toBeNull();
    await user.click(within(h3).getByRole("tab", { name: "绑定" }));
    expect(h3).toHaveTextContent("用的是 DramaStudio 输入 / 输出节点");
    expect(within(h3).queryByRole("combobox")).toBeNull();
    expect(within(h3).getAllByText("DramaStudio 节点")).toHaveLength(10);
  });

  it("guessed bindings block the trial and the tier until confirmed", async () => {
    const user = userEvent.setup();
    renderLibrary();
    const wan = await open(user, WAN);
    expect(within(wan).getByRole("tab", { name: "绑定", selected: true })).toBeInTheDocument();
    expect(wan).toHaveTextContent("还有 3 项是导入时自动猜的，确认后才能试跑和登记。");
    expect(within(wan).getByRole("button", { name: "升为我的工作流" })).toBeDisabled();
    expect(wan).toHaveTextContent("先确认绑定");

    // Point the seed at the other sampler, then confirm everything.
    const seedNode = within(wan).getByRole("combobox", { name: "种子 的节点" });
    await user.selectOptions(seedNode, "KSampler (low noise)");
    expect(within(wan).getByRole("combobox", { name: "种子 的字段" })).toHaveValue("noise_seed");
    await user.click(within(wan).getByRole("button", { name: "确认全部绑定" }));
    expect(await screen.findByText("绑定已确认")).toBeInTheDocument();
    await waitFor(() => expect(header(WAN)).toHaveTextContent("正常"));
    const saved = getDb().workflows.find((w) => w.id === "wf_wan");
    expect(saved?.bindings.every((b) => b.state === "confirmed")).toBe(true);
    expect(saved?.bindings.find((b) => b.slot === "seed")?.node_title).toBe("KSampler (low noise)");

    // Now the trial can run; once it passes, the workflow can become 我的工作流.
    expect(row(WAN)).toHaveTextContent("先试跑通过");
    await user.click(within(row(WAN)).getByRole("tab", { name: "试跑" }));
    await user.click(within(row(WAN)).getByRole("button", { name: "试跑" }));
    expect(await screen.findByText("已开始试跑：Wan 2.2 图生视频（社区）")).toBeInTheDocument();
    expect(await within(row(WAN)).findByText("试跑中…（本地 GPU 队列）")).toBeInTheDocument();
    const promote = await within(row(WAN)).findByRole(
      "button",
      { name: "通过了，升为我的工作流" },
      { timeout: 3000 },
    );
    await user.click(promote);
    expect(await screen.findByText("已升为「我的工作流」：Wan 2.2 图生视频（社区）")).toBeVisible();
    await waitFor(() => expect(header(WAN)).toHaveTextContent("我的工作流"));
  });

  it("missing node packs and models install after the ComfyUI change list", async () => {
    const user = userEvent.setup();
    renderLibrary();
    const kontext = await open(user, KONTEXT);
    expect(within(kontext).getByRole("tab", { name: "体检", selected: true })).toBeVisible();
    expect(kontext).toHaveTextContent("上次体检 2026-10-18 09:25 · 节点类 17/19 在");
    const packs = within(kontext).getByRole("table", { name: "缺的节点包" });
    expect(within(packs).getByRole("row", { name: /ComfyUI-GGUF/ })).toHaveTextContent(
      "UnetLoaderGGUFregistry1.1.4",
    );
    const models = within(kontext).getByRole("table", { name: "缺的模型" });
    expect(within(models).getByRole("row", { name: /flux1-kontext/ })).toHaveTextContent("11.8 GB");
    await user.click(within(row(KONTEXT)).getByRole("tab", { name: "试跑" }));
    expect(within(row(KONTEXT)).getByRole("button", { name: "试跑" })).toBeDisabled();
    expect(row(KONTEXT)).toHaveTextContent("先装好缺的节点包和模型");
    await user.click(within(row(KONTEXT)).getByRole("tab", { name: "体检" }));

    await user.click(
      within(row(KONTEXT)).getByRole("button", { name: "安装缺的 2 个节点包和 1 个模型" }),
    );
    const dialog = await screen.findByRole("alertdialog", { name: "开始安装前请确认" });
    expect(within(dialog).getByText("会改动你的 ComfyUI（3 项）")).toBeInTheDocument();
    expect(within(dialog).getByRole("row", { name: /^ComfyUI-GGUF/ })).toHaveTextContent(
      "安装1.1.4https://github.com/city96/ComfyUI-GGUF",
    );
    expect(within(dialog).getByRole("row", { name: /flux1-kontext/ })).toHaveTextContent(
      "约 11.8 GB",
    );
    expect(dialog).toHaveTextContent("装坏了可以在「环境与安装」里一键回滚");
    await user.click(within(dialog).getByRole("button", { name: "确认，开始安装" }));
    expect(
      await screen.findByText(/^已存快照 .*，装好了 2 个节点包、1 个模型$/),
    ).toBeInTheDocument();
    await waitFor(() => expect(header(KONTEXT)).toHaveTextContent("正常"));
    expect(row(KONTEXT)).toHaveTextContent("都在：节点类、被绑定的节点标题和字段、模型文件。");
  });

  it("imports from ComfyUI's list; the asset board and imported ones cannot be picked", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByRole("rowgroup", { name: WAN });
    await user.click(screen.getByRole("button", { name: "导入工作流" }));
    const dialog = await screen.findByRole("dialog", { name: "导入工作流" });
    const file = (path: string) => within(dialog).getByRole("listitem", { name: path });
    expect(
      await within(dialog).findByRole("listitem", { name: "短剧/雨停之前/第1集-素材板.json" }),
    ).toHaveTextContent("素材板，不能登记");
    expect(file("video_wan2_2_14B_i2v.json")).toHaveTextContent("已导入");
    expect(within(file("video_wan2_2_14B_i2v.json")).queryByRole("button")).toBeNull();
    await user.click(within(file("我的/雨夜氛围-ltx2.json")).getByRole("button", { name: "导入" }));
    expect(await screen.findByText("已导入「雨夜氛围-ltx2」：先确认绑定，再试跑")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const added = await screen.findByRole("rowgroup", { name: "雨夜氛围-ltx2" });
    expect(added).toHaveTextContent("导入自 我的/雨夜氛围-ltx2.json");
    expect(added).toHaveTextContent("还有 8 项是导入时自动猜的");
    expect(within(added).getByRole("button", { name: "展开 雨夜氛围-ltx2" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("imports a dropped API-format JSON and refuses other files", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByRole("rowgroup", { name: WAN });
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

  it("my workflows can go back to unverified", async () => {
    const user = userEvent.setup();
    renderLibrary();
    const lip = await open(user, "LatentSync 口型");
    await user.click(within(lip).getByRole("button", { name: "降为未验证" }));
    expect(await screen.findByText("已降为未验证：LatentSync 口型")).toBeVisible();
    await waitFor(() => expect(header("LatentSync 口型")).toHaveTextContent("未验证"));
  });

  it("switches to English", async () => {
    act(() => useUiStore.getState().toggleLang());
    try {
      renderLibrary();
      expect(await screen.findByRole("region", { name: "Workflow library" })).toBeInTheDocument();
      const wan = await screen.findByRole("rowgroup", { name: WAN });
      expect(screen.getByRole("radio", { name: "Unverified 2" })).toBeInTheDocument();
      expect(wan).toHaveTextContent("Unverified3 bindings to confirmNever run");
    } finally {
      act(() => useUiStore.getState().toggleLang());
    }
  });
});
