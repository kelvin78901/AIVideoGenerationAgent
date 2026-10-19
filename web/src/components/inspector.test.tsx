import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { Route, Routes } from "react-router";

import { useImpactPreview } from "@/api/hooks/impact";
import type { ImpactAction } from "@/api/schemas/impact";
import { useEventStream } from "@/api/useEventStream";
import { GateButton } from "@/components/GateButton";
import { ImpactDialog } from "@/components/ImpactDialog";
import { Inspector } from "@/components/Inspector";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { PRODUCT_ENRICH, PRODUCT_EXTRACT } from "@/mocks/fixtures/demo/products";
import { useInspectorStore } from "@/stores/inspector";
import { backend } from "@/test/backend";
import { fakeConfig } from "@/test/fakes/config";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

// Page wording passed to GateButton (pages own it).
const TO_STORYBOARD = "去做分镜";
const CONFIRM_NOVEL = "确认原文";

const NOVEL = [
  { id: "enrich", productId: PRODUCT_ENRICH },
  { id: "extract", productId: PRODUCT_EXTRACT },
];

function override(component = "enrich") {
  return fakeConfig.component[component];
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

function Panel({ item = null }: { item?: string | null }) {
  useEventStream();
  return <Inspector components={NOVEL} item={item} />;
}

describe("Inspector", () => {
  it("shows the component chips and switches between components", async () => {
    const user = userEvent.setup();
    renderAt(<Panel />);
    expect(await screen.findByRole("heading", { name: "小说补全" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "设定提取" }));
    expect(await screen.findByRole("heading", { name: "设定提取" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "本地" })).toBeChecked();
  });

  it("opens a tab from outside (RunBar's 历史 / 改提示词)", async () => {
    renderAt(<Panel />);
    await screen.findByRole("heading", { name: "小说补全" });
    act(() => useInspectorStore.getState().show("history"));
    expect(await screen.findByRole("tab", { name: "历史 2", selected: true })).toBeInTheDocument();
    expect(await screen.findByText(/小说补全 的全部版本/)).toBeInTheDocument();
    act(() => useInspectorStore.getState().show("prompt", "extract"));
    expect(await screen.findByRole("heading", { name: "设定提取 · 提示词" })).toBeInTheDocument();
  });
});

describe("ModelPicker", () => {
  it("greys out run locations that cannot be used and says why", async () => {
    const def = fakeConfig.catalog.components.find((c) => c.id === "enrich");
    if (def) def.local_models = [];
    renderAt(<Panel />);
    await screen.findByRole("heading", { name: "小说补全" });
    expect(await screen.findByRole("radio", { name: "本地" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "混合" })).toBeDisabled();
    expect(screen.getByText("本地：这个组件没有可本地运行的模型")).toBeInTheDocument();
    expect(screen.getByText("混合：混合需要本地和 API 都能用")).toBeInTheDocument();
    expect(screen.getByText("这个组件没有可本地运行的模型。")).toBeInTheDocument();
  });

  it("lists 6 API services and expands 「更多供应商（8）」", async () => {
    const user = userEvent.setup();
    renderAt(<Panel />);
    const api = await screen.findByRole("radiogroup", { name: "API 服务" });
    expect(within(api).getAllByRole("radio")).toHaveLength(6);
    expect(within(api).getByRole("radio", { name: /DeepSeek V4 Pro/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "更多供应商（8）" }));
    expect(within(api).getAllByRole("radio")).toHaveLength(14);
    expect(screen.getByRole("button", { name: "收起" })).toBeInTheDocument();
  });

  it("writes changes as component overrides and labels their source", async () => {
    const user = userEvent.setup();
    renderAt(<Panel />);
    const api = await screen.findByRole("radiogroup", { name: "API 服务" });
    expect(screen.getAllByTestId("config-source")[0]).toHaveTextContent("预设");
    await user.click(within(api).getByRole("radio", { name: /Kimi K2.6/ }));
    await waitFor(() => expect(override()?.api_model).toBe("moonshot/kimi-k2.6"));
    await waitFor(() =>
      expect(screen.getAllByTestId("config-source")[1]).toHaveTextContent("组件"),
    );
    // The rerun estimate follows the new route (the backend prices it on read).
    await user.click(screen.getByRole("radio", { name: "本地" }));
    await waitFor(() => expect(override()?.mode).toBe("local"));
    expect(await screen.findByText(/^无 API 费用 · /)).toBeInTheDocument();
  });

  it("toggles fallback, its triggers and its target", async () => {
    const user = userEvent.setup();
    renderAt(<Panel />);
    expect(
      await screen.findByText("主用的 DeepSeek V4 Pro 出问题时，自动改用 Kimi K2.6，并记进历史。"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /自动质检连续 2 次不过/ }));
    await waitFor(() => expect(override()?.fallback?.on).toContain("qa_fail"));
    const targets = screen.getByRole("radiogroup", { name: "兜底到" });
    await user.click(within(targets).getByRole("radio", { name: "Qwen3.8-max" }));
    await waitFor(() => expect(override()?.fallback?.to).toBe("qwen/qwen3.8-max"));
    expect(await screen.findByText(/自动改用 Qwen3.8-max/)).toBeInTheDocument();
    await user.click(screen.getByRole("switch", { name: /自动兜底/ }));
    expect(await screen.findByText("已关闭：出问题时停下来等你处理。")).toBeInTheDocument();
    expect(override()?.fallback?.enabled).toBe(false);
    expect(screen.queryByRole("radiogroup", { name: "兜底到" })).not.toBeInTheDocument();
  });

  it("saves the per-call cap", async () => {
    const user = userEvent.setup();
    renderAt(<Panel />);
    const cap = await screen.findByLabelText("单次花费上限（美元）");
    expect(cap).toHaveValue(0.5);
    await user.clear(cap);
    await user.type(cap, "1.5");
    await user.tab();
    await waitFor(() => expect(override()?.per_call_cap_usd).toBe(1.5));
  });

  it("overrides one item without touching the component", async () => {
    const user = userEvent.setup();
    renderAt(<Panel item="shot:1-05" />);
    await user.click(await screen.findByRole("radio", { name: "混合" }));
    await waitFor(() => expect(fakeConfig.item["enrich|shot:1-05"]?.mode).toBe("hybrid"));
    expect(override()).toBeUndefined();
    await waitFor(() =>
      expect(screen.getAllByTestId("config-source")[0]).toHaveTextContent("单项"),
    );
  });

  it("flags API models without a key outside Mock mode", async () => {
    backend({ mock: false });
    renderAt(<Panel />);
    const api = await screen.findByRole("radiogroup", { name: "API 服务" });
    await waitFor(() =>
      expect(within(api).getByRole("radio", { name: /DeepSeek V4 Pro/ })).toHaveTextContent(
        "未填密钥",
      ),
    );
    expect(within(api).getByRole("radio", { name: /Kimi K2.6/ })).not.toHaveTextContent("未填密钥");
  });
});

/** Previews the 9:16 → 16:9 change on mount, like the spec page will. */
function SpecImpact({
  variant,
  onResolved,
}: {
  variant: "inline" | "modal";
  onResolved: (a: ImpactAction) => void;
}) {
  const preview = useImpactPreview();
  const { mutate } = preview;
  useEffect(() => {
    mutate({ kind: "spec_aspect", target_id: "demo", patch: { aspect: "16:9" } });
  }, [mutate]);
  if (!preview.data) return null;
  return (
    <ImpactDialog
      impact={preview.data}
      variant={variant}
      title="16:9"
      onResolved={(a) => onResolved(a)}
    />
  );
}

describe("ImpactDialog", () => {
  it("lists what is affected with costs; 「只标记」 marks the steps 待更新", async () => {
    const user = userEvent.setup();
    const resolved = vi.fn();
    renderAt(<SpecImpact variant="inline" onResolved={resolved} />);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("关键帧 9 张（9 个镜头）要按新画幅重画 · 约 $1.26");
    expect(dialog).toHaveTextContent("API 终版 · 约 $2.76");
    expect(dialog).toHaveTextContent("建议重出（可选）");
    expect(dialog).toHaveTextContent("剧本、分镜表、配音和音色不受影响");
    await user.click(within(dialog).getByRole("button", { name: "只标记待更新" }));
    await waitFor(() => expect(resolved).toHaveBeenCalledWith("mark"));
    const steps = getDb().progress[EP1]?.steps;
    expect(steps?.storyboard.stale).toBe(9);
    expect(steps?.generate.stale).toBe(10);
  });

  it("「自动重跑」 shows the total and queues the rerun", async () => {
    const user = userEvent.setup();
    const resolved = vi.fn();
    renderAt(<SpecImpact variant="modal" onResolved={resolved} />);
    const dialog = await screen.findByRole("alertdialog");
    await user.click(
      within(dialog).getByRole("button", { name: "自动重跑受影响的部分 · 预计 $4.02" }),
    );
    await waitFor(() => expect(resolved).toHaveBeenCalledWith("rerun"));
    expect(getDb().progress[EP1]?.steps.storyboard.stale).toBe(9);
  });

  it("「撤销修改」 leaves everything as it was", async () => {
    const user = userEvent.setup();
    const resolved = vi.fn();
    renderAt(<SpecImpact variant="inline" onResolved={resolved} />);
    await user.click(await screen.findByRole("button", { name: "撤销修改" }));
    await waitFor(() => expect(resolved).toHaveBeenCalledWith("undo"));
    expect(getDb().progress[EP1]?.steps.storyboard.stale).toBe(0);
  });
});

describe("GateButton", () => {
  function Pages() {
    return (
      <Routes>
        <Route
          path="/s/demo/e/1/assets"
          element={
            <GateButton
              gate="assets"
              episodeId={EP1}
              label={TO_STORYBOARD}
              to="/s/demo/e/1/storyboard"
            />
          }
        />
        <Route
          path="/s/demo/e/1/novel"
          element={
            <GateButton
              gate="novel"
              episodeId={EP1}
              label={CONFIRM_NOVEL}
              to="/s/demo/e/1/script"
            />
          }
        />
        <Route path="/s/demo/e/1/storyboard" element={<div data-testid="next-step" />} />
      </Routes>
    );
  }

  it("confirms the gate and goes to the next step", async () => {
    const user = userEvent.setup();
    renderAt(<Pages />, "/s/demo/e/1/assets");
    const button = await screen.findByRole("button", { name: "去做分镜" });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    expect(await screen.findByTestId("next-step")).toBeInTheDocument();
    expect(getDb().progress[EP1]?.steps.assets.state).toBe("confirmed");
    expect(getDb().gates.at(-1)).toMatchObject({ gate: "assets", action: "confirm" });
  });

  it("shows a confirmed step and reopens it", async () => {
    const user = userEvent.setup();
    renderAt(<Pages />, "/s/demo/e/1/novel");
    expect(await screen.findByText("已确认")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重新打开" }));
    await waitFor(() => expect(screen.queryByText("已确认")).not.toBeInTheDocument());
    expect(getDb().progress[EP1]?.steps.novel.state).toBe("in_progress");
  });
});
