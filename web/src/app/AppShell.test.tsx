import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { AppRoutes } from "@/app/routes";
import i18n from "@/i18n";
import { series } from "@/mocks/fixtures/demo/series";
import { server } from "@/mocks/node";
import { useUiStore } from "@/stores/ui";
import { backend, fake } from "@/test/backend";
import { makeJob } from "@/test/fixtures";
import { renderAt } from "@/test/render";
import { fakeSetup, installState, resetFakeSetup } from "@/test/setupBackend";

beforeEach(() => {
  act(() => useUiStore.setState({ lang: "zh-CN", theme: "light", lastSeries: null }));
  backend();
});

describe("AppShell", () => {
  it("redirects / to the first-run page until the machine has been scanned", async () => {
    renderAt(<AppRoutes />, "/");
    expect(
      await screen.findByRole("heading", { level: 1, name: "先看看这台电脑能跑什么" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "环境与安装" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("redirects / to the first step of the demo episode once scanned", async () => {
    resetFakeSetup("pc", { scanned: true });
    renderAt(<AppRoutes />, "/");
    expect(await screen.findByRole("heading", { level: 1, name: "小说" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /01\s*小说/ })).toHaveAttribute("aria-current", "page");
  });

  it("/ goes back to the series opened last, else the newest", async () => {
    resetFakeSetup("pc", { scanned: true });
    fake.created.push({ ...series, id: "s1", slug: "s1", title: "新剧" });
    act(() => useUiStore.setState({ lastSeries: "demo" }));
    const { unmount } = renderAt(<AppRoutes />, "/");
    expect(await screen.findByText("177 字 · 5 段")).toBeInTheDocument();
    expect(screen.getByTestId("shell-title")).toHaveTextContent("《雨停之前》");
    unmount();
    // A series that is gone: the newest one.
    act(() => useUiStore.setState({ lastSeries: "gone" }));
    renderAt(<AppRoutes />, "/");
    expect(await screen.findByText("还没有导入小说")).toBeInTheDocument();
    expect(screen.getByTestId("shell-title")).toHaveTextContent("《新剧》");
    expect(useUiStore.getState().lastSeries).toBe("s1");
  });

  it("/ offers to start a series when there is none", async () => {
    resetFakeSetup("pc", { scanned: true });
    server.use(http.get("*/api/v1/series", () => HttpResponse.json([])));
    renderAt(<AppRoutes />, "/");
    expect(
      await screen.findByRole("heading", { level: 1, name: "开始一部剧" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "新建剧集…" }));
    expect(await screen.findByRole("dialog", { name: "新建剧集" })).toBeInTheDocument();
  });

  it("the series menu switches series and creates one, then opens its spec", async () => {
    const user = userEvent.setup();
    fake.created.push({ ...series, id: "s1", slug: "s1", title: "新剧" });
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    await user.click(
      await screen.findByRole("button", {
        name: "《雨停之前》",
        description: "切换剧集或新建剧集",
      }),
    );
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.textContent),
    ).toEqual(["《新剧》", "《雨停之前》", "新建剧集…"]);
    expect(within(menu).getByRole("menuitem", { name: "《雨停之前》" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    await user.click(within(menu).getByRole("menuitem", { name: "《新剧》" }));
    expect(await screen.findByText("还没有导入小说")).toBeInTheDocument();
    expect(screen.getByTestId("shell-title")).toHaveTextContent("《新剧》");

    await user.click(screen.getByRole("button", { description: "切换剧集或新建剧集" }));
    await user.click(await screen.findByRole("menuitem", { name: "新建剧集…" }));
    const dialog = await screen.findByRole("dialog", { name: "新建剧集" });
    await user.click(within(dialog).getByRole("button", { name: "创建，去定成片规格" }));
    expect(within(dialog).getByText("剧名不能为空")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("剧名"), "  旧发圈 ");
    await user.click(within(dialog).getByRole("button", { name: "创建，去定成片规格" }));
    expect(await screen.findByRole("heading", { level: 1, name: "成片规格" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("shell-title")).toHaveTextContent("《旧发圈》"));
    expect(fake.created.at(-1)).toMatchObject({ id: "s2", title: "旧发圈" });
    expect(useUiStore.getState().lastSeries).toBe("s2");
    // The spec page leads on to importing the novel.
    expect(screen.getByRole("link", { name: "下一步：导入小说" })).toHaveAttribute(
      "href",
      "/s/s2/e/1/novel",
    );
  });

  it("deep links never jump to the first-run page", async () => {
    renderAt(<AppRoutes />, "/models");
    expect(screen.getByRole("heading", { level: 1, name: "模型与兜底" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("gpu-status")).toHaveTextContent("RTX 5090"));
    expect(screen.getByRole("heading", { level: 1, name: "模型与兜底" })).toBeInTheDocument();
  });

  it("keeps 环境与安装 first among the tools, with what is missing as its badge", async () => {
    renderAt(<AppRoutes />, "/s/demo/spec");
    const nav = screen.getByRole("navigation", { name: "制作步骤" });
    const tools = within(nav)
      .getAllByRole("link")
      .map((a) => a.textContent)
      .filter((text) => !/^\d\d/.test(text ?? ""));
    expect(tools.slice(0, 2)).toEqual(["环境与安装", "成片规格"]);
    expect(within(nav).getByRole("link", { name: "环境与安装" })).toHaveAttribute("href", "/setup");
    // Nothing before the first scan.
    expect(screen.queryByTestId("setup-badge")).toBeNull();
  });

  it("counts required items still missing or outdated, in both languages", async () => {
    resetFakeSetup("pc", { scanned: true });
    renderAt(<AppRoutes />, "/s/demo/spec");
    expect(await screen.findByTestId("setup-badge")).toHaveTextContent("缺 11 项");
    expect(screen.getByRole("link", { name: /^环境与安装\s*缺 11 项$/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "切换界面语言 / Switch language" }));
    expect(screen.getByTestId("setup-badge")).toHaveTextContent("11 missing");
    expect(screen.getByRole("link", { name: /^Environment\s*11 missing$/ })).toBeInTheDocument();
  });

  it("hides the badge once everything required is there", async () => {
    resetFakeSetup("pc", { scanned: true });
    for (const x of fakeSetup.profile.items)
      if (x.status === "missing" || x.status === "old") x.install = installState("done", 100);
    renderAt(<AppRoutes />, "/s/demo/spec");
    await waitFor(() => expect(screen.getByTestId("gpu-status")).toHaveTextContent("RTX 5090"));
    expect(screen.queryByTestId("setup-badge")).toBeNull();
  });

  it("renders every SPEC 16.1 route", () => {
    const cases: [string, string][] = [
      ["/setup", "先看看这台电脑能跑什么"],
      ["/models", "模型与兜底"],
      ["/s/demo/spec", "成片规格"],
      ["/s/demo/sync", "素材整理与同步"],
      ["/s/demo/dashboard", "数据看板"],
      ["/s/demo/e/1/novel", "小说"],
      ["/s/demo/e/1/script", "剧本"],
      ["/s/demo/e/1/assets", "素材"],
      ["/s/demo/e/1/storyboard", "分镜"],
      ["/s/demo/e/1/generate", "生成"],
      ["/s/demo/e/1/post", "后期"],
      ["/nope", "页面不存在"],
    ];
    for (const [path, title] of cases) {
      const { unmount } = renderAt(<AppRoutes />, path);
      expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
      unmount();
    }
  });

  it("keeps the series and episode in nav links; spec tag comes from the series spec", async () => {
    renderAt(<AppRoutes />, "/s/demo/e/2/script");
    expect(screen.getByRole("link", { name: /03\s*素材/ })).toHaveAttribute(
      "href",
      "/s/demo/e/2/assets",
    );
    expect(await screen.findByRole("link", { name: "9:16 · 1080×1920 · 24 fps" })).toHaveAttribute(
      "href",
      "/s/demo/spec",
    );
    expect(screen.getByRole("link", { name: "数据看板" })).toHaveAttribute(
      "href",
      "/s/demo/dashboard",
    );
  });

  it("shows series, episode, spend and budget from the API", async () => {
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    expect(await screen.findByText(/第 1 集《红伞》/)).toBeInTheDocument();
    expect(screen.getByTestId("shell-title")).toHaveTextContent("《雨停之前》 · 第 1 集《红伞》");
    await waitFor(() =>
      expect(screen.getByTestId("spend")).toHaveTextContent("本集 API 花费 $8.94 / 预算 $15"),
    );
  });

  it("does not show a spend of $0 when the summary is missing", async () => {
    server.use(
      http.get("*/api/v1/metrics/summary", () =>
        HttpResponse.json({ code: "not_found", params: {} }, { status: 404 }),
      ),
    );
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    await waitFor(() =>
      expect(screen.getByTestId("spend")).toHaveTextContent("本集 API 花费 — / 预算 $15"),
    );
  });

  it("shows step badges from the episode progress", async () => {
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    await waitFor(() => expect(screen.getAllByTestId("step-badge")).toHaveLength(6));
    expect(screen.getAllByTestId("step-badge").map((b) => b.textContent)).toEqual([
      "已确认",
      "已确认",
      "7/13",
      "3/9",
      "3/9",
      "未开始",
    ]);
    await userEvent.click(screen.getByRole("button", { name: "切换界面语言 / Switch language" }));
    expect(screen.getAllByTestId("step-badge")[5]).toHaveTextContent("Not started");
  });

  it("shows 同步中 on the steps a 确认并同步 is still rerunning", async () => {
    const cascade = { id: "sync-1", origin: "demo-novel" };
    server.use(
      http.get("*/api/v1/jobs", () =>
        HttpResponse.json([
          makeJob({
            id: "j1",
            series_id: "demo",
            component_id: "split",
            state: "running",
            params: { cascade },
          }),
          // Episode 2's script, and a run of its own: not this episode's sync.
          makeJob({
            id: "j2",
            series_id: "demo",
            episode_id: "demo-e2",
            component_id: "script",
            params: { cascade },
          }),
          makeJob({ id: "j3", series_id: "demo", component_id: "extract", state: "running" }),
        ]),
      ),
    );
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    await waitFor(() => expect(screen.getAllByTestId("step-badge")[1]).toHaveTextContent("同步中"));
    expect(screen.getAllByTestId("step-badge")[0]).toHaveTextContent("已确认");
  });

  it("switches language from the top bar", async () => {
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    await userEvent.click(screen.getByRole("button", { name: "切换界面语言 / Switch language" }));
    expect(i18n.language).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(screen.getByRole("heading", { level: 1, name: "Novel" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Production steps" })).toBeInTheDocument();
    expect(screen.getByTestId("gpu-status")).toHaveTextContent(/^Local GPU: .*idle$/);
  });

  it("shows the Mock badge only in mock mode, in both languages", async () => {
    const idle = { gpuRunning: 0, gpuQueued: 0 };
    const { unmount } = renderAt(<AppRoutes status={{ ...idle, mock: false }} />, "/models");
    expect(screen.queryByTestId("mock-badge")).not.toBeInTheDocument();
    unmount();
    renderAt(<AppRoutes status={{ ...idle, mock: true }} />, "/models");
    expect(screen.getByTestId("mock-badge")).toHaveTextContent("Mock 模式");
    await userEvent.click(screen.getByRole("button", { name: "切换界面语言 / Switch language" }));
    expect(screen.getByTestId("mock-badge")).toHaveTextContent("Mock mode");
  });

  it("shows the GPU name from the machine profile and live GPU activity", async () => {
    renderAt(<AppRoutes status={{ gpuRunning: 1, gpuQueued: 2 }} />, "/models");
    expect(screen.getByTestId("gpu-status")).toHaveTextContent("本地 GPU：运行中 1 · 排队 2");
    await waitFor(() =>
      expect(screen.getByTestId("gpu-status")).toHaveTextContent(
        "本地 GPU：RTX 5090 32GB · 运行中 1 · 排队 2",
      ),
    );
  });

  it("shows the demo-data badge once the page displays demo responses", async () => {
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    expect(await screen.findByTestId("demo-badge")).toHaveTextContent("示例数据");
    await userEvent.click(screen.getByRole("button", { name: "切换界面语言 / Switch language" }));
    expect(screen.getByTestId("demo-badge")).toHaveTextContent("Demo data");
  });

  it("hides the demo-data badge when every response is real", async () => {
    // A real backend answering everything (here: only the series, without the demo header).
    server.use(
      http.get("*/api/v1/series/:id", () => HttpResponse.json(series)),
      http.get("*/api/v1/*", () => HttpResponse.json(null, { status: 404 })),
    );
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    expect(await screen.findByText("《雨停之前》")).toBeInTheDocument();
    expect(screen.queryByTestId("demo-badge")).not.toBeInTheDocument();
  });
});
