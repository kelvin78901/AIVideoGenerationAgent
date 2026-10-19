import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useProduct } from "@/api/hooks/products";
import { useEventStream } from "@/api/useEventStream";
import { CostBadge } from "@/components/CostBadge";
import { PromptEditor } from "@/components/PromptEditor";
import { RunBar } from "@/components/RunBar";
import { VersionHistory } from "@/components/VersionHistory";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { llmModels } from "@/mocks/fixtures/demo/models";
import { demoAt, demoProduct, demoVersion } from "@/mocks/fixtures/demo/products";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

// Page-provided content (not UI copy in these components).
const WHAT = "补全建议 · 4 条";
const NAME = "小说补全";

/** Element `i` of a list, failing the test when it is missing. */
function at<T>(list: readonly T[], i: number): T {
  const item = list[i];
  if (item === undefined) throw new Error(`no item ${i}`);
  return item;
}

/**
 * A product the MSW demo runs (rerun, switch, adopt, prompt): the prototype's 小说补全 history,
 * v1 Qwen3.6-27B 本地 09:41 → v2 DeepSeek V4 Pro 10:02（不满意换一个）已采纳. (The demo series'
 * real 小说补全 is the backend's now; these tests are about the shared product views.)
 */
const PRODUCT = "test-p-enrich";

function seedProduct() {
  const at = (n: number, origin: "run" | "switch", model: string, hhmm: string) =>
    demoVersion(PRODUCT, "enrich", {
      n,
      origin,
      model,
      at: demoAt(hhmm),
      payload: { suggestions: 4 },
    });
  const v1 = at(1, "run", "local/qwen3.6-27b", "09:41");
  const v2 = { ...at(2, "switch", "deepseek/v4-pro", "10:02"), parent_version_id: v1.id };
  getDb().products[PRODUCT] = demoProduct(PRODUCT, "enrich", "suggestions", [v1, v2], 40);
}

/** The novel page's wiring in miniature: events on, one product, the three product views. */
function Harness({ id = PRODUCT }: { id?: string }) {
  useEventStream();
  const product = useProduct(id);
  if (!product.data) return null;
  return (
    <>
      <RunBar
        product={product.data}
        what={WHAT}
        models={llmModels}
        onEditPrompt={() => {}}
        onOpenHistory={() => {}}
      />
      <VersionHistory product={product.data} models={llmModels} componentName={NAME} />
      <PromptEditor product={product.data} componentName={NAME} />
    </>
  );
}

function enrich() {
  const p = getDb().products[PRODUCT];
  if (!p) throw new Error("demo product missing");
  return p;
}
const history = () => screen.getByRole("list", { name: /历史/ });
const items = async () =>
  within(await screen.findByRole("list", { name: /历史/ })).getAllByRole("listitem");

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  demoTiming.runMs = 20;
  seedProduct();
});
afterEach(() => {
  vi.unstubAllGlobals();
  demoTiming.runMs = 1400;
});

describe("RunBar", () => {
  it("shows the current version and the rerun estimate", async () => {
    renderAt(<Harness />);
    expect(await screen.findByText("当前产物 · 补全建议 · 4 条")).toBeInTheDocument();
    expect(screen.getByText(/v2 · DeepSeek V4 Pro/)).toHaveTextContent("已采纳");
    expect(screen.getByRole("button", { name: /^重跑/ })).toHaveTextContent("≈$0.02");
    expect(screen.getByRole("button", { name: "历史 2" })).toBeInTheDocument();
  });

  it("rerun appends v3 with the same model and origin=rerun", async () => {
    // Long enough that the running state is still on screen when a loaded runner looks for it.
    demoTiming.runMs = 300;
    const user = userEvent.setup();
    renderAt(<Harness />);
    await user.click(await screen.findByRole("button", { name: /^重跑/ }));
    expect(await screen.findByText("正在用 DeepSeek V4 Pro 生成…")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "历史 3" }, { timeout: 3000 }),
    ).toBeInTheDocument();
    const v3 = at(enrich().versions, 2);
    expect(v3).toMatchObject({ n: 3, origin: "rerun", model_key: "deepseek/v4-pro" });
    expect(enrich().current_version_id).toBe(v3.id);
    // The adopted version does not change by itself (hard rule 5).
    expect(enrich().adopted_version_id).toBe(`${PRODUCT}-v2`);
    expect(screen.queryByRole("status", { name: /生成/ })).not.toBeInTheDocument();
  });

  it("「不满意换一个」 lists the other models and reruns with origin=switch", async () => {
    const user = userEvent.setup();
    renderAt(<Harness />);
    await user.click(await screen.findByRole("button", { name: /不满意换一个/ }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByText("DeepSeek V4 Pro")).not.toBeInTheDocument();
    expect(within(menu).getByText("$0.95 / $4 每百万 token")).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: /Kimi K2.6/ }));
    await screen.findByRole("button", { name: "历史 3" });
    expect(at(enrich().versions, 2)).toMatchObject({
      origin: "switch",
      model_key: "moonshot/kimi-k2.6",
      parent_version_id: `${PRODUCT}-v2`,
    });
    expect(within(history()).getAllByRole("listitem")[0]).toHaveTextContent("不满意换一个");
  });
});

describe("VersionHistory", () => {
  it("lists versions newest first and marks the current one", async () => {
    renderAt(<Harness />);
    const list = await items();
    expect(list.map((li) => li.textContent?.slice(0, 2))).toEqual(["v2", "v1"]);
    expect(list[0]).toHaveAttribute("aria-current", "true");
    expect(list[0]).toHaveTextContent("已采纳 · 当前");
    expect(list[1]).toHaveTextContent("无 API 费用");
    expect(list[1]).toHaveTextContent("初版");
    // Demo times are wall-clock times in the viewer's zone (prototype: 09:41).
    expect(list[1]).toHaveTextContent("09:41");
  });

  it("adopting a version replaces the previous adoption", async () => {
    const user = userEvent.setup();
    renderAt(<Harness />);
    const v1 = at(await items(), 1);
    await user.click(within(v1).getByRole("button", { name: "采纳这一版" }));
    await waitFor(() => expect(v1).toHaveTextContent("已采纳 · 当前"));
    const v2 = at(within(history()).getAllByRole("listitem"), 0);
    expect(v2).toHaveTextContent("草稿");
    expect(within(v2).getByRole("button", { name: "采纳这一版" })).toBeEnabled();
    expect(enrich().adopted_version_id).toBe(`${PRODUCT}-v1`);
  });

  it("set current changes what is shown, not what is adopted", async () => {
    const user = userEvent.setup();
    renderAt(<Harness />);
    const v1 = at(await items(), 1);
    await user.click(within(v1).getByRole("button", { name: "设为当前" }));
    await waitFor(() => expect(screen.getByText(/v1 · Qwen3.6-27B/)).toBeInTheDocument());
    expect(enrich().adopted_version_id).toBe(`${PRODUCT}-v2`);
  });

  it("disables adopting on a locked product", async () => {
    enrich().locked_hash = "sha256:x";
    enrich().status = "locked";
    renderAt(<Harness />);
    const list = await items();
    expect(list[0]).toHaveTextContent("已锁定");
    expect(within(at(list, 1)).getByRole("button", { name: "采纳这一版" })).toBeDisabled();
  });
});

describe("PromptEditor", () => {
  it("previews the compiled prompt and follows the intent", async () => {
    const user = userEvent.setup();
    renderAt(<Harness />);
    const preview = await screen.findByTestId("compiled-preview");
    expect(preview).toHaveTextContent("# 目标模型：DeepSeek V4 Pro");
    const intent = screen.getByLabelText("你的要求（意图层）");
    await user.clear(intent);
    await user.type(intent, "只补光线");
    await waitFor(() => expect(preview).toHaveTextContent("[规则] 只补光线"));
  });

  it("marks a hand-edited compiled layer and restores automatic compiling", async () => {
    const user = userEvent.setup();
    renderAt(<Harness />);
    await user.click(await screen.findByRole("button", { name: /查看 \/ 修改编译后的提示词/ }));
    const compiled = screen.getByLabelText(/编译层（直接改/);
    await user.type(compiled, "\n额外规则");
    expect(screen.getByText("已手动修改编译层")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "恢复自动编译" }));
    expect(screen.queryByText("已手动修改编译层")).not.toBeInTheDocument();
    expect(compiled).not.toHaveValue(expect.stringContaining("额外规则"));
  });

  it("「只保存」 stores the prompt for the next run without a new version", async () => {
    const user = userEvent.setup();
    renderAt(<Harness />);
    await user.click(await screen.findByRole("button", { name: /查看 \/ 修改编译后的提示词/ }));
    await user.type(screen.getByLabelText(/编译层（直接改/), "\n额外规则");
    await user.click(screen.getByRole("button", { name: "只保存" }));
    await waitFor(() => expect(enrich().prompt?.compiled_overridden).toBe(true));
    expect(enrich().prompt?.compiled).toContain("额外规则");
    expect(enrich().versions).toHaveLength(2);
  });

  it("「保存并重跑」 runs with the edited intent", async () => {
    const user = userEvent.setup();
    renderAt(<Harness />);
    const intent = await screen.findByLabelText("你的要求（意图层）");
    await user.clear(intent);
    await user.type(intent, "只补光线");
    await user.click(screen.getByRole("button", { name: "保存并重跑" }));
    await screen.findByRole("button", { name: "历史 3" });
    const v3 = at(enrich().versions, 2);
    expect(v3).toMatchObject({ origin: "rerun", intent: "只补光线", compiled_overridden: false });
    expect(v3.compiled).toContain("只补光线");
    expect(within(history()).getAllByRole("listitem")[0]).toHaveTextContent("改提示词后重跑");
  });
});

describe("CostBadge", () => {
  it.each([
    [{ where: "local" as const }, "无 API 费用"],
    [{ where: "local" as const, compact: true }, "免费"],
    [{ where: "api" as const, usd: 0.4 }, "$0.40"],
    [{ where: "api" as const, usd: 0.02, estimate: true, seconds: 40 }, "预计 ≈$0.02 · 约 40 秒"],
    [{ where: "api" as const, usd: 1.26, estimate: true, seconds: 300 }, "预计 ≈$1.26 · 约 5 分钟"],
    [{ where: "api" as const, price: null }, "按量计费"],
    [
      { where: "api" as const, price: { unit: "mtok", in: 6, out: 30, currency: "CNY" } as const },
      "¥6 / ¥30 每百万 token",
    ],
    [
      { where: "api" as const, price: { unit: "second", amount: 0.1, currency: "USD" } as const },
      "$0.10 / 秒",
    ],
  ])("%o → %s", (props, text) => {
    renderAt(<CostBadge {...props} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });
});
