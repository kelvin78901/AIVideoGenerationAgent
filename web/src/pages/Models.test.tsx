import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { Toaster } from "@/components/ui/sonner";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { server } from "@/mocks/node";
import ModelsPage from "@/pages/Models";
import { backend } from "@/test/backend";
import { fakeConfig } from "@/test/fakes/config";
import { fakeEpisodes } from "@/test/fakes/episodes";
import { renderAt } from "@/test/render";

const renderModels = () =>
  renderAt(
    <>
      <ModelsPage />
      <Toaster />
    </>,
    "/models",
  );

const row = (name: string) => screen.getByRole("rowgroup", { name });
const mode = (name: string, m: string) =>
  within(within(row(name)).getByRole("radiogroup", { name: `${name} 的运行位置` })).getByRole(
    "radio",
    { name: m },
  );
const ready = async () => {
  await screen.findByRole("rowgroup", { name: "字幕对齐" });
  await waitFor(() => expect(mode("小说补全", "API")).toBeChecked());
};
const preset = (name: RegExp) => screen.getByRole("button", { name });

beforeEach(() => backend());

describe("ModelsPage", () => {
  it("shows the balanced preset, every component and the video row open", async () => {
    renderModels();
    await ready();
    expect(preset(/^均衡/)).toHaveAttribute("aria-pressed", "true");
    expect(preset(/^均衡/)).toHaveTextContent("当前");
    const components = screen.getByRole("table", { name: "组件设置" });
    expect(within(components).getAllByRole("rowgroup")).toHaveLength(20);
    expect(mode("设定提取", "本地")).toBeChecked();
    expect(row("设定提取")).toHaveTextContent("Qwen3.6-27B");
    expect(row("参考图生成")).toHaveTextContent("Qwen-Image-Edit（本地） → Nano Banana Pro");
    expect(row("3D 场景（可选）")).toHaveTextContent("这一步不跑");
    expect(mode("结构控制", "API")).toBeDisabled();
    expect(within(row("视频生成")).getByRole("button", { name: "收起 视频生成" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const order = within(row("视频生成")).getByRole("list", { name: "「不满意换一个」的顺序" });
    expect(within(order).getAllByRole("listitem")[0]).toHaveTextContent("Seedance 2.5");
    expect(screen.getByText(/本地：RTX 5090 32GB · ComfyUI 已连接/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "重新检测主机、补装缺少的组件" })).toHaveAttribute(
      "href",
      "/setup",
    );
  });

  it("does not claim a GPU or connected services when that data is missing", async () => {
    const missing = () => HttpResponse.json({ code: "not_found", params: {} }, { status: 404 });
    server.use(
      http.get("*/api/v1/config/components", missing),
      http.get("*/api/v1/setup/profile", missing),
    );
    renderModels();
    expect(
      await screen.findByText("本地：未知 · ComfyUI 未知 · 推理服务 未知"),
    ).toBeInTheDocument();
  });

  it("presets re-route every component; 全本地 skips what has no local version", async () => {
    const user = userEvent.setup();
    renderModels();
    await ready();
    await user.click(preset(/^省钱/));
    expect(await screen.findByText("已切到「省钱」。手动改过的组件保持不变。")).toBeInTheDocument();
    await waitFor(() => expect(mode("小说补全", "本地")).toBeChecked());
    expect(row("小说补全")).toHaveTextContent("DeepSeek V4.1 Flash");
    expect(fakeConfig.defaults.preset).toBe("cheap");

    await user.click(preset(/^全本地/));
    await waitFor(() =>
      expect(row("3D 场景（可选）")).toHaveTextContent("没有本地版本，这一步跳过"),
    );
    expect(within(row("小说补全")).getByRole("switch")).not.toBeChecked();
    expect(row("小说补全")).toHaveTextContent("关闭");
  });

  it("a hand-changed component keeps its setting across presets until reset", async () => {
    const user = userEvent.setup();
    renderModels();
    await ready();
    await user.click(mode("小说补全", "本地"));
    expect(await within(row("小说补全")).findByText("已手动改过，不跟随预设")).toBeInTheDocument();
    await user.click(preset(/^质量优先/));
    await waitFor(() => expect(mode("设定提取", "API")).toBeChecked());
    expect(mode("小说补全", "本地")).toBeChecked();

    await user.click(within(row("小说补全")).getByRole("button", { name: "展开 小说补全" }));
    await user.click(within(row("小说补全")).getByRole("button", { name: "恢复成预设" }));
    expect(await screen.findByText("「小说补全」已恢复成预设。")).toBeInTheDocument();
    await waitFor(() => expect(mode("小说补全", "API")).toBeChecked());
    expect(within(row("小说补全")).queryByText("已手动改过，不跟随预设")).toBeNull();
    expect(fakeConfig.component.enrich).toBeUndefined();
  });

  it("reorders alternatives and picks the fallback target", async () => {
    const user = userEvent.setup();
    renderModels();
    await ready();
    const vid = row("视频生成");
    await user.click(within(vid).getByRole("button", { name: "下移 Seedance 2.5" }));
    await waitFor(() =>
      expect(fakeConfig.component.vid?.alt_order?.slice(0, 2)).toEqual([
        "google/gemini-omni-flash-1.1",
        "volc/seedance-2.5",
      ]),
    );
    const order = within(vid).getByRole("list", { name: "「不满意换一个」的顺序" });
    await waitFor(() =>
      expect(within(order).getAllByRole("listitem")[0]).toHaveTextContent("Gemini Omni Flash 1.1"),
    );
    expect(
      within(order).getByRole("button", { name: "上移 Gemini Omni Flash 1.1" }),
    ).toBeDisabled();

    const targets = within(vid).getByRole("radiogroup", { name: "兜底到" });
    await user.click(within(targets).getByRole("radio", { name: "Seedance 2.5" }));
    await waitFor(() => expect(fakeConfig.component.vid?.fallback?.to).toBe("volc/seedance-2.5"));
    await user.click(within(row("小说补全")).getByRole("switch", { name: "小说补全 自动兜底" }));
    await waitFor(() => expect(row("小说补全")).toHaveTextContent("关闭"));
  });

  it("fallback policy and the episode budget", async () => {
    const user = userEvent.setup();
    renderModels();
    await ready();
    const policy = screen.getByRole("radiogroup", { name: "兜底方式" });
    await user.click(within(policy).getByRole("radio", { name: "兜底前先问我" }));
    expect(await screen.findByText(/先暂停这一步，弹出提示让你选/)).toBeInTheDocument();
    expect(fakeConfig.defaults.fallback_notify).toBe("ask");

    const budget = screen.getByLabelText("本集 API 预算 $");
    expect(budget).toHaveValue(15);
    await user.clear(budget);
    await user.type(budget, "20{Enter}");
    expect(await screen.findByText("本集 API 预算改成 $20。")).toBeInTheDocument();
    // The backend keeps it; the top bar's summary reads it from there.
    expect(fakeEpisodes.episodePatches).toEqual([{ id: EP1, budget_usd: 20 }]);
    expect(fakeEpisodes.list.find((e) => e.id === EP1)?.budget_usd).toBe(20);
  });

  it("saves a provider key and tests the connection (real backend endpoints)", async () => {
    const user = userEvent.setup();
    let hasKey = false;
    const sent: unknown[] = [];
    const provider = () => ({
      id: "deepseek",
      name: "DeepSeek",
      where: "api",
      base_url: "https://api.deepseek.com",
      docs: null,
      verify: true,
      needs_key: true,
      has_key: hasKey,
      key_source: hasKey ? "keyring" : "none",
      enabled: true,
      models: [],
    });
    server.use(
      http.get("*/api/v1/providers", () =>
        HttpResponse.json({ providers: [provider()], llm_ui_order: [] }),
      ),
      http.post("*/api/v1/providers/deepseek/key", async ({ request }) => {
        sent.push(await request.json());
        hasKey = true;
        return HttpResponse.json(provider());
      }),
      http.post("*/api/v1/providers/deepseek/test", () =>
        HttpResponse.json({ ok: true, detail: null, models: ["deepseek-chat", "deepseek-r2"] }),
      ),
    );
    renderModels();
    await user.click(await screen.findByRole("button", { name: "DeepSeek · 未配置" }));
    const dialog = await screen.findByRole("dialog", { name: "DeepSeek 的 API 密钥" });
    expect(within(dialog).getByText("还没配置")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "测试连接" })).toBeDisabled();
    await user.type(within(dialog).getByLabelText("API 密钥"), "sk-test-123");
    await user.click(within(dialog).getByRole("button", { name: "保存" }));
    expect(await screen.findByText("DeepSeek 的密钥已保存。")).toBeInTheDocument();
    expect(sent).toEqual([{ api_key: "sk-test-123" }]);
    expect(await within(dialog).findByText("已配置（系统钥匙串）")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("API 密钥")).toHaveValue("");
    await user.click(within(dialog).getByRole("button", { name: "测试连接" }));
    expect(await within(dialog).findByText("连接正常，能看到 2 个模型。")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(await screen.findByRole("button", { name: "DeepSeek · 已配置" })).toBeInTheDocument();
  });
});
