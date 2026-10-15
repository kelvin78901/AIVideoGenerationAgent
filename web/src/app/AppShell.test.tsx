import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { AppRoutes } from "@/app/routes";
import i18n from "@/i18n";
import { series } from "@/mocks/fixtures/demo/series";
import { server } from "@/mocks/node";
import { useUiStore } from "@/stores/ui";
import { renderAt } from "@/test/render";

beforeEach(() => {
  act(() => useUiStore.setState({ lang: "zh-CN", theme: "light" }));
});

describe("AppShell", () => {
  it("redirects / to the first step of the demo episode", () => {
    renderAt(<AppRoutes />, "/");
    expect(screen.getByRole("heading", { level: 1, name: "小说" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /01\s*小说/ })).toHaveAttribute("aria-current", "page");
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
