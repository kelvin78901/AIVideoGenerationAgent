import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AppRoutes } from "@/app/routes";
import i18n from "@/i18n";
import { useUiStore } from "@/stores/ui";
import { renderAt } from "@/test/render";

beforeEach(() => {
  act(() => useUiStore.setState({ lang: "zh-CN", theme: "light" }));
});

describe("AppShell", () => {
  it("redirects / to the first step of the demo episode", () => {
    renderAt(<AppRoutes />, "/");
    expect(screen.getByRole("heading", { name: "小说 · 导入与补全" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /01\s*小说/ })).toHaveAttribute("aria-current", "page");
  });

  it("renders every SPEC 16.1 route", () => {
    const cases: [string, string][] = [
      ["/setup", "首次启动 · 主机检测与自动安装"],
      ["/models", "模型与兜底 · 全局默认"],
      ["/s/demo/spec", "成片规格"],
      ["/s/demo/sync", "素材整理与同步"],
      ["/s/demo/dashboard", "数据看板 · 花费、耗时与速度"],
      ["/s/demo/e/1/novel", "小说 · 导入与补全"],
      ["/s/demo/e/1/script", "剧本 · 分集与剧本化"],
      ["/s/demo/e/1/assets", "素材 · 角色、场景、道具、文字、音色"],
      ["/s/demo/e/1/storyboard", "分镜 · 关键帧与镜头设定"],
      ["/s/demo/e/1/generate", "生成 · 候选墙与自动质检"],
      ["/s/demo/e/1/post", "后期 · 时间线与导出"],
      ["/nope", "页面不存在"],
    ];
    for (const [path, title] of cases) {
      const { unmount } = renderAt(<AppRoutes />, path);
      expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
      unmount();
    }
  });

  it("keeps the series in nav links and the spec tag", () => {
    renderAt(<AppRoutes />, "/s/rain/e/2/script");
    expect(screen.getByRole("link", { name: /03\s*素材/ })).toHaveAttribute(
      "href",
      "/s/rain/e/2/assets",
    );
    expect(screen.getByRole("link", { name: "9:16 · 1080×1920 · 24 fps" })).toHaveAttribute(
      "href",
      "/s/rain/spec",
    );
    expect(screen.getByRole("link", { name: "数据看板" })).toHaveAttribute(
      "href",
      "/s/rain/dashboard",
    );
  });

  it("switches language from the top bar", async () => {
    renderAt(<AppRoutes />, "/s/demo/e/1/novel");
    await userEvent.click(screen.getByRole("button", { name: "切换界面语言 / Switch language" }));
    expect(i18n.language).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(screen.getByRole("heading", { name: "Novel · Import and enrich" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Production steps" })).toBeInTheDocument();
    expect(screen.getByText("Local GPU: idle")).toBeInTheDocument();
  });

  it("shows GPU activity and spend", () => {
    renderAt(
      <AppRoutes status={{ gpuRunning: 1, gpuQueued: 2, spentUsd: 8.94, budgetUsd: 15 }} />,
      "/models",
    );
    expect(screen.getByTestId("gpu-status")).toHaveTextContent("本地 GPU：运行中 1 · 排队 2");
    expect(screen.getByText("$8.94")).toBeInTheDocument();
    expect(screen.getByText(/预算 \$15\.00/)).toBeInTheDocument();
  });
});
