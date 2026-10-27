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
    expect(within(components).getAllByRole("rowgroup")).toHaveLength(22);
    expect(mode("设定提取", "本地")).toBeChecked();
    expect(row("设定提取")).toHaveTextContent("Qwen3.6-27B");
    expect(row("参考图生成")).toHaveTextContent("Qwen-Image（本地） → Nano Banana Pro");
    // 补视图 edits the locked picture: the editing model, locally, on the official 40 steps.
    expect(row("补视图")).toHaveTextContent("Qwen-Image-Edit 40 步（本地）");
    // OCR runs on this computer only: no API to switch to.
    expect(row("文字核对（OCR）")).toHaveTextContent("RapidOCR（本地）");
    expect(mode("文字核对（OCR）", "API")).toBeDisabled();
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

  it("tests the image models that share a provider's key", async () => {
    const user = userEvent.setup();
    const google = {
      id: "google_llm",
      name: "Google（Gemini）",
      where: "api",
      base_url: "https://generativelanguage.googleapis.com/v1beta/openai/",
      docs: null,
      verify: false,
      needs_key: true,
      has_key: true,
      key_source: "keyring",
      enabled: true,
      models: [],
      media: [
        {
          key: "google/nano-banana-pro",
          display: "Nano Banana Pro",
          model_id: "gemini-3-pro-image",
          custom_model_id: false,
        },
      ],
    };
    const settings: unknown[] = [];
    server.use(
      http.get("*/api/v1/providers", () =>
        HttpResponse.json({ providers: [google], llm_ui_order: [] }),
      ),
      http.put("*/api/v1/providers/settings/*", async ({ request }) => {
        settings.push({ url: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json({ model_key: "x", model_id: "y", price: null });
      }),
      http.post("*/api/v1/providers/google_llm/test", () =>
        HttpResponse.json({
          ok: true,
          detail: null,
          models: ["gemini-3.6-flash"],
          media: [
            {
              key: "google/nano-banana-pro",
              display: "Nano Banana Pro",
              ok: false,
              detail: "model_not_found",
            },
          ],
        }),
      ),
    );
    renderModels();
    await user.click(await screen.findByRole("button", { name: "Google（Gemini） · 已配置" }));
    const dialog = await screen.findByRole("dialog", { name: "Google（Gemini） 的 API 密钥" });
    expect(
      within(dialog).getByRole("heading", { name: "用这个密钥的媒体模型" }),
    ).toBeInTheDocument();
    const id = within(dialog).getByLabelText("Nano Banana Pro");
    expect(id).toHaveValue("gemini-3-pro-image");
    await user.clear(id);
    await user.type(id, "gemini-3.5-pro-image");
    await user.click(within(dialog).getByRole("button", { name: "保存" }));
    await waitFor(() =>
      expect(settings).toEqual([
        {
          url: "/api/v1/providers/settings/google/nano-banana-pro",
          body: { model_id: "gemini-3.5-pro-image" },
        },
      ]),
    );
    await user.click(within(dialog).getByRole("button", { name: "测试连接" }));
    expect(await within(dialog).findByText("连接正常，能看到 1 个模型。")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Nano Banana Pro：不能用（model_not_found）"),
    ).toBeInTheDocument();
  });

  it("switches a provider's site, picks listed models and prices one", async () => {
    const user = userEvent.setup();
    let site = "cn";
    let picked = ["kimi-k3.1-pro"];
    let own: { in: number; out: number; currency: string } | null = null;
    const calls: unknown[] = [];
    const listed = () =>
      site !== "cn"
        ? null
        : {
            site: "cn",
            fetched_at: "2026-10-26T08:00:00Z",
            models: [
              {
                model_id: "kimi-k3.1-pro",
                key: "moonshot/kimi-k3.1-pro",
                display: "Kimi K3.1 Pro",
                in_table: true,
                enabled: picked.includes("kimi-k3.1-pro"),
                price: { in: 13, out: 68, currency: "CNY" },
                price_source: "table",
              },
              {
                model_id: "kimi-k2.7-code",
                key: "moonshot/kimi-k2.7-code",
                display: "kimi-k2.7-code",
                in_table: false,
                enabled: picked.includes("kimi-k2.7-code"),
                price: own,
                price_source: own ? "user" : null,
              },
            ],
          };
    const moonshot = () => ({
      id: "moonshot",
      name: "Moonshot（Kimi）",
      where: "api",
      site,
      sites: [
        { id: "cn", base_url: "https://api.moonshot.cn/v1", docs: null, has_key: true },
        { id: "intl", base_url: "https://api.moonshot.ai/v1", docs: null, has_key: false },
      ],
      base_url: site === "cn" ? "https://api.moonshot.cn/v1" : "https://api.moonshot.ai/v1",
      docs: null,
      verify: false,
      needs_key: true,
      has_key: site === "cn",
      key_source: site === "cn" ? "keyring" : "none",
      enabled: true,
      models: [],
      listed: listed(),
      media: [],
    });
    server.use(
      http.get("*/api/v1/providers", () =>
        HttpResponse.json({ providers: [moonshot()], llm_ui_order: [] }),
      ),
      http.put("*/api/v1/providers/moonshot/models", async ({ request }) => {
        const body = (await request.json()) as { enabled: string[] };
        calls.push({ models: body.enabled });
        picked = body.enabled;
        return HttpResponse.json(moonshot());
      }),
      http.put("*/api/v1/providers/settings/*", async ({ request }) => {
        const body = (await request.json()) as { price: typeof own };
        calls.push({ price: body.price });
        own = body.price;
        return HttpResponse.json({
          model_key: "moonshot/kimi-k2.7-code",
          model_id: null,
          price: own,
        });
      }),
      http.patch("*/api/v1/providers/moonshot", async ({ request }) => {
        const body = (await request.json()) as { site: string };
        calls.push({ site: body.site });
        site = body.site;
        return HttpResponse.json(moonshot());
      }),
    );
    renderModels();
    await user.click(await screen.findByRole("button", { name: "Moonshot（Kimi） · 已配置" }));
    const dialog = await screen.findByRole("dialog", { name: "Moonshot（Kimi） 的 API 密钥" });
    const sites = within(dialog).getByRole("radiogroup", { name: "站点" });
    expect(within(sites).getByRole("radio", { name: "国内站 · 已有密钥" })).toBeChecked();
    expect(within(dialog).getByText("共 2 个，勾了 1 个", { exact: false })).toBeInTheDocument();
    expect(within(dialog).getByText("参考价 ¥13 / ¥68 每百万 token")).toBeInTheDocument();
    expect(within(dialog).getByText("价格未知")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("checkbox", { name: /kimi-k2\.7-code/ }));
    await waitFor(() =>
      expect(within(dialog).getByRole("checkbox", { name: /kimi-k2\.7-code/ })).toBeChecked(),
    );
    await user.click(within(dialog).getByRole("button", { name: "给 kimi-k2.7-code 填价格" }));
    const form = within(dialog).getByRole("form", { name: "kimi-k2.7-code 的单价" });
    await user.type(within(form).getByLabelText("输入"), "4");
    await user.type(within(form).getByLabelText("输出"), "16");
    await user.click(within(form).getByRole("button", { name: "保存" }));
    expect(await within(dialog).findByText("你填的 ¥4 / ¥16 每百万 token")).toBeInTheDocument();

    await user.click(within(sites).getByRole("radio", { name: "国际站" }));
    expect(await screen.findByText("Moonshot（Kimi） 改用国际站。")).toBeInTheDocument();
    expect(
      await within(dialog).findByText("测试连接后会列出这家的全部模型", { exact: false }),
    ).toBeInTheDocument();
    expect(calls).toEqual([
      { models: ["kimi-k3.1-pro", "kimi-k2.7-code"] },
      { price: { in: 4, out: 16, currency: "CNY" } },
      { site: "intl" },
    ]);
  });
});
