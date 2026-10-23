import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { Toaster } from "@/components/ui/sonner";
import SpecPage from "@/pages/Spec";
import { backend, fake } from "@/test/backend";
import { fakeShots } from "@/test/fakes/shots";
import { renderAt } from "@/test/render";

function renderSpec() {
  return renderAt(
    <Routes>
      <Route
        path="/s/:series/spec"
        element={
          <>
            <SpecPage />
            <Toaster />
          </>
        }
      />
    </Routes>,
    "/s/demo/spec",
  );
}

const spec = () => fake.spec;
const group = (name: string) => screen.getByRole("group", { name });
const aspect = (name: RegExp) => within(group("画幅")).getByRole("button", { name });
const ready = () => screen.findByRole("button", { name: /国内短剧平台/ });
const compatRow = (stage: string) => screen.getByRole("row", { name: new RegExp(`^${stage}`) });

beforeEach(() => backend());

describe("SpecPage", () => {
  it("shows the saved spec: platform, aspect, sizes, compat, locked", async () => {
    renderSpec();
    await ready();
    expect(screen.getByRole("button", { name: /国内短剧平台/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /横屏平台/ })).toHaveTextContent("16:9 · 1920×1080");
    expect(aspect(/^9:16 竖版/)).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("radio", { name: "1080p 1080×1920" })).toBeChecked();
    expect(screen.getByText(/草稿固定用 768p 档（768×1366）/)).toBeInTheDocument();
    expect(
      await screen.findByRole("row", { name: /^关键帧 Nano Banana Pro 原生支持/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("已锁定 · 第 1 集已有 9 个镜头")).toBeInTheDocument();
    expect(screen.getByText("48 kHz · 响度 -14 LUFS · 峰值 -1 dBTP")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /安全区预览：9:16 竖版，顶部栏、按钮、标题/ }),
    ).toBeInTheDocument();
  });

  it("a new aspect on a locked spec shows the impact first; saving is held until resolved", async () => {
    const user = userEvent.setup();
    renderSpec();
    await ready();
    await user.click(aspect(/^21:9 宽银幕/));
    expect(await screen.findByText("改成 21:9 宽银幕 会影响已经做好的部分")).toBeInTheDocument();
    expect(screen.getByText(/关键帧 7 张（9 个镜头）要按新画幅重画/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "改，并自动重做（约 $0.94）" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /自定义/ })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() =>
      expect(compatRow("视频（备选）")).toHaveTextContent("支持这个画幅；部分渠道只到 720p"),
    );
    expect(screen.getByTestId("zone-controlsWide")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存规格" }));
    expect(await screen.findByText("先在上面的提示里选怎么处理已生成的内容。")).toBeInTheDocument();
    expect(spec().aspect).toBe("9:16");
  });

  it("撤销 keeps 9:16", async () => {
    const user = userEvent.setup();
    renderSpec();
    await ready();
    await user.click(aspect(/^16:9 横版/));
    await user.click(await screen.findByRole("button", { name: "撤销，保持 9:16" }));
    await waitFor(() => expect(aspect(/^9:16 竖版/)).toHaveAttribute("aria-pressed", "true"));
    expect(screen.queryByText(/会影响已经做好的部分/)).toBeNull();
    expect(screen.getByRole("button", { name: /国内短剧平台/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(spec().aspect).toBe("9:16");
  });

  it("「改，并标记待更新」 writes the aspect and marks downstream work", async () => {
    const user = userEvent.setup();
    renderSpec();
    await ready();
    await user.click(screen.getByRole("button", { name: /横屏平台/ }));
    await user.click(await screen.findByRole("button", { name: "改，并标记待更新" }));
    await waitFor(() => expect(spec().aspect).toBe("16:9"));
    expect(spec().platform).toBe("wide");
    expect(spec().dims.delivery).toEqual({ w: 1920, h: 1080 });
    // The confirmed shots go back to 待确认 (their keyframes were drawn for 9:16).
    expect(fakeShots.shots.filter((s) => s.confirmed)).toEqual([]);
    await waitFor(() => expect(screen.queryByText(/会影响已经做好的部分/)).toBeNull());
  });

  it("saves resolution, frame rate, length, subtitles and the derived version", async () => {
    const user = userEvent.setup();
    renderSpec();
    await ready();
    await user.click(screen.getByRole("radio", { name: "2K 1440×2560" }));
    await user.click(within(group("帧率")).getByRole("button", { name: "25 fps" }));
    expect(screen.getByText(/从 24 fps 转成 25 fps/)).toBeInTheDocument();
    await user.click(within(group("每集时长")).getByRole("button", { name: "1.5–3 分钟" }));
    await user.click(within(group("字幕")).getByRole("button", { name: "烧进画面" }));
    await user.click(screen.getByRole("checkbox", { name: /另出一版横屏（16:9）/ }));
    await user.click(screen.getByRole("button", { name: "保存规格" }));
    await waitFor(() =>
      expect(spec()).toMatchObject({
        delivery: "2k",
        fps: 25,
        episode_len: "mid",
        subtitles: "burn",
        derive: "16:9",
        dims: { delivery: { w: 1440, h: 2560 } },
      }),
    );
    expect(await screen.findByText("已保存：9:16 · 1440×2560 · 25 fps。")).toBeInTheDocument();
  });

  it("toggles the overlays and the subtitle position", async () => {
    const user = userEvent.setup();
    renderSpec();
    await ready();
    expect(screen.getByTestId("zone-buttons")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "显示平台遮挡区（示意）" }));
    expect(screen.queryByTestId("zone-buttons")).toBeNull();
    await user.click(screen.getByRole("checkbox", { name: "显示字幕位置" }));
    expect(screen.queryByTestId("sub-position")).toBeNull();
  });

  it("an unlocked spec changes aspect directly on save", async () => {
    spec().locked_at = null;
    const user = userEvent.setup();
    renderSpec();
    await ready();
    await user.click(aspect(/^3:4 竖版/));
    expect(screen.queryByText(/会影响已经做好的部分/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "保存规格" }));
    await waitFor(() => expect(spec().aspect).toBe("3:4"));
    expect(spec().dims.delivery).toEqual({ w: 1080, h: 1440 });
  });
});
