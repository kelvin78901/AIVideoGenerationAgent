import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { niceTicks } from "@/components/charts/scale";
import { Toaster } from "@/components/ui/sonner";
import DashboardPage from "@/pages/Dashboard";
import { backend } from "@/test/backend";
import { renderAt } from "@/test/render";

const renderDashboard = () =>
  renderAt(
    <Routes>
      <Route path="/s/:series/dashboard" element={<DashboardPage />} />
    </Routes>,
    "/s/demo/dashboard",
  );

const card = (name: string) => screen.getByRole("region", { name });
const readout = (region: HTMLElement) => region.querySelector("[data-readout]")?.textContent ?? "";
const spendCard = () => card("累计 API 花费（美元）");
const callsCard = () => card("API 调用次数（每 15 分钟）");

beforeEach(() => backend());

describe("DashboardPage", () => {
  it("shows the budget card, insights and KPIs with the prototype's numbers", async () => {
    renderDashboard();
    const budget = await screen.findByRole("region", { name: "预算" });
    expect(within(budget).getByTestId("hero-spent")).toHaveTextContent("$8.94");
    expect(budget).toHaveTextContent("预计本集 $13.35 · 预算 $15");
    expect(budget).toHaveTextContent("预计还要 $4.41");
    expect(budget).toHaveTextContent("预计在预算内，剩 $1.65");
    expect(within(budget).getByRole("img")).toHaveAccessibleName(
      "已花 $8.94，预计本集 $13.35，预算 $15",
    );
    const insights = within(budget).getAllByRole("listitem").slice(-3);
    expect(insights[0]).toHaveTextContent(
      "音色设计 $3.04、参考图和画面文字 $1.68，合计占已花的 53%",
    );
    expect(insights[2]).toHaveTextContent("Seedance 2.5 每秒 $0.41，是 H3 API 的 5 倍");

    const kpis = await screen.findByRole("region", { name: "关键指标" });
    const tile = (name: string) => within(kpis).getByRole("group", { name });
    expect(tile("已采纳成片")).toHaveTextContent("10 秒共 34 秒 · 9 个镜头采纳了 3 个");
    expect(tile("每秒成片成本")).toHaveTextContent("$0.89");
    expect(tile("本地 GPU 运行")).toHaveTextContent(
      "2 小时 12 分另外等 API 44 分钟 · 显存峰值 29.6 GB",
    );
    expect(tile("API 调用")).toHaveTextContent("42 次成功 41 次（97.6%）· 1 次限流已重试");
    expect(tile("质检通过")).toHaveTextContent("6 / 10 条");
    expect(tile("镜头从开始到采纳")).toHaveTextContent("中位 19 分钟最慢的 1-04 已用 38 分钟");
    expect(screen.getByText("第 1 集《红伞》 · 场 1–2 · 9 个镜头")).toBeInTheDocument();
  });

  it("switches the scope to the whole series", async () => {
    renderDashboard();
    await screen.findByRole("region", { name: "预算" });
    await userEvent.click(screen.getByRole("radio", { name: "全剧" }));
    expect(await screen.findByText("全剧已花（API）")).toBeInTheDocument();
    expect(card("预算")).toHaveTextContent("预计全剧 $28.05 · 预算 $45");
    expect(
      screen.getByText("全剧 3 集，目前只有第 1 集在跑，下面的图都是第 1 集的数据"),
    ).toBeInTheDocument();
  });

  it("links hover between the spend line and the call columns", async () => {
    renderDashboard();
    await screen.findByRole("region", { name: "累计 API 花费（美元）" });
    // Before hovering both readouts show the latest bucket.
    expect(readout(spendCard())).toContain("11:45–11:55（最近一段）");
    expect(readout(spendCard())).toContain(
      "新增 $1.65，累计 $8.94。1-04 换 Seedance 2.5 出 T4 $1.64",
    );
    expect(readout(callsCard())).toContain("文本 0 次 · 图像 0 次 · 音视频 1 次，花了 $1.65");
    expect(spendCard().querySelector("[data-crosshair]")).toBeNull();

    const column = within(callsCard()).getByRole("button", {
      name: "10:30–10:45：文本 2 次 · 图像 6 次 · 音视频 3 次",
    });
    await userEvent.hover(column);
    expect(column).toHaveAttribute("aria-pressed", "true");
    expect(spendCard().querySelector("[data-crosshair]")).not.toBeNull();
    expect(readout(spendCard())).toContain("10:30–10:45 · 新增 $3.89，累计 $4.01。音色设计 $3.02");
    expect(readout(callsCard())).toContain(
      "10:30–10:45 · 文本 2 次 · 图像 6 次 · 音视频 3 次，花了 $3.89",
    );

    // Hovering the spend strip of the failed bucket moves the columns too.
    await userEvent.hover(
      within(spendCard()).getByRole("button", { name: "11:30–11:45，新增 $0.33，累计 $7.29" }),
    );
    expect(readout(callsCard())).toContain("失败 1 次");
    expect(within(callsCard()).getByRole("button", { name: /^11:30–11:45/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await userEvent.unhover(spendCard());
    expect(readout(callsCard())).toContain("（最近一段）");
  });

  it("table views carry the same numbers as the charts", async () => {
    renderDashboard();
    await screen.findByRole("region", { name: "累计 API 花费（美元）" });

    const strips = within(spendCard())
      .getAllByRole("button")
      .filter((b) => b.hasAttribute("aria-pressed"));
    await userEvent.click(within(spendCard()).getByRole("radio", { name: "表" }));
    const rows = within(within(spendCard()).getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(strips.length);
    expect(rows[4]).toHaveTextContent("10:30–10:45$3.89$4.01");
    expect(rows.at(-1)).toHaveTextContent("11:45–11:55$1.65$8.94");

    const columns = within(callsCard()).getAllByRole("button", { name: /：/ });
    await userEvent.click(within(callsCard()).getByRole("radio", { name: "表" }));
    const callRows = within(within(callsCard()).getByRole("table")).getAllByRole("row").slice(1);
    expect(callRows).toHaveLength(columns.length);
    const sum = (col: number) =>
      callRows.reduce((n, r) => n + Number(r.querySelectorAll("td")[col]?.textContent), 0);
    expect([sum(1), sum(2), sum(3), sum(4)]).toEqual([15, 17, 10, 1]);
  });

  it("follows the SPEC 11.3 drawing rules", async () => {
    renderDashboard();
    await screen.findByRole("region", { name: "API 调用次数（每 15 分钟）" });
    for (const region of [spendCard(), callsCard()])
      expect(region.querySelectorAll('[data-axis="y"]')).toHaveLength(1);
    const segments = callsCard().querySelectorAll<HTMLElement>("[data-segment]");
    expect(segments.length).toBeGreaterThan(0);
    for (const s of segments) expect(parseFloat(s.style.width)).toBeLessThanOrEqual(24);
    // Three call kinds → a legend with three entries; text stays in text colours.
    const [legend] = within(callsCard()).getAllByRole("list");
    if (!legend) throw new Error("no legend");
    expect(
      within(legend)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["文本 15 次 · $0.20", "图像 17 次 · $2.94", "音视频 10 次 · $5.80"]);
    expect(callsCard()).toHaveTextContent("失败 1");
  });
});

describe("niceTicks", () => {
  it("picks clean steps", () => {
    expect(niceTicks(11)).toEqual({ ticks: [0, 4, 8, 12], top: 12 });
    expect(niceTicks(15)).toEqual({ ticks: [0, 5, 10, 15], top: 15 });
    expect(niceTicks(45)).toEqual({ ticks: [0, 20, 40, 60], top: 60 });
    expect(niceTicks(0)).toEqual({ ticks: [0, 1], top: 1 });
  });
});

describe("DashboardPage · lower half", () => {
  it("groups shots by scene and shows the clicked shot's details", async () => {
    renderDashboard();
    const shots = await screen.findByRole("region", { name: "每个镜头花了多少时间和钱" });
    expect(shots).toHaveTextContent("场 1 · 楼道5 个镜头 · 已采纳 3 · 108 分钟 · $4.02");
    expect(shots).toHaveTextContent("场 2 · 出租屋4 个镜头 · 已采纳 0 · 7 分钟 · $0.00");
    // 1-04 (the shot waiting for a pick) is open by default.
    expect(readout(shots)).toContain(
      "1-04 林晚：……周屿？ · 关键帧 4 分 · 视频生成 31 分 · 质检与精修 3 分 · 花费 $1.96 · 候选 4 条",
    );
    expect(readout(shots)).toContain(
      "T1 本地 7.5 分钟（人脸、手指没过） → 自动重跑 T2 本地 7.5 分钟 → T3 本地 10 分钟超时，兜底到 H3 API 1 分钟 → 换 Seedance 2.5 出 T4 3 分钟（灯光没过）。",
    );
    expect(within(shots).getByRole("button", { name: /^1-08/ })).toHaveTextContent(
      "等 1-06 采纳，要它的尾帧",
    );
    await userEvent.click(within(shots).getByRole("button", { name: /^1-02/ }));
    expect(readout(shots)).toContain("本地草稿质检没过（颜色），API 终版通过。");

    await userEvent.click(within(shots).getByRole("radio", { name: "表" }));
    const rows = within(within(shots).getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(9);
    expect(rows[3]).toHaveTextContent("1-044313384$1.96待挑选");
  });

  it("shows components, speed, APIs, local models, QA and episodes", async () => {
    renderDashboard();
    const comps = await screen.findByRole("region", { name: "各组件累计计算时长（分钟）" });
    expect(comps).toHaveTextContent("本地 132 分钟，等 API 44 分钟");
    expect(
      within(comps).getByRole("img", { name: "视频生成：本地 51 分钟，API 12 分钟" }),
    ).toBeInTheDocument();

    const speed = card("出 1 秒成片要算多少秒");
    expect(
      within(speed).getByRole("img", {
        name: "MiniMax H3（本地）：中位 112 秒，最快 98，最慢 150",
      }),
    ).toBeInTheDocument();
    expect(speed).toHaveTextContent("中位 112 秒4 秒约 7.5 分钟");
    expect(speed).toHaveTextContent("API · $0.41 / 秒");

    const apis = card("各 API 的调用和花费");
    const apiRows = within(apis).getAllByRole("row");
    expect(apiRows[1]).toHaveTextContent("MiniMax Speech 2.8 HD");
    expect(apiRows[1]).toHaveTextContent("$3.04 34%");
    expect(apiRows[4]).toHaveTextContent("1 次 429 限流，已自动重试");
    expect(apiRows[4]).toHaveTextContent("80.0%");
    expect(apiRows[3]).toHaveTextContent("3 分 10 秒");
    expect(apiRows.at(-1)).toHaveTextContent("合计4297.6%$8.94");

    const local = card("本地模型：跑了多久、占多少显存");
    expect(
      within(local).getByRole("img", { name: "MiniMax H3 显存峰值 29.6 GB，共 32 GB" }),
    ).toBeInTheDocument();
    expect(local).toHaveTextContent("Qwen3.6-27B小说补全、设定提取、剧本化49 分钟18.9 GB");

    const qa = card("自动质检");
    expect(within(qa).getByRole("img", { name: "通过 6 条，未过 4 条" })).toBeInTheDocument();
    expect(qa).toHaveTextContent("通过 6未过 4自动重跑 1 · 自动兜底 1 · 手动换模型 1");

    const episodes = card("按集汇总");
    const epRows = within(episodes).getAllByRole("row");
    expect(epRows[1]).toHaveTextContent(
      "第 1 集《红伞》进行中10 / 34 秒$8.94约 $13.352 小时 56 分",
    );
    expect(epRows[2]).toHaveTextContent("约 $7.10（素材复用）");
    expect(epRows.at(-1)).toHaveTextContent("全剧合计10 / 约 184 秒$8.94约 $28.052 小时 56 分");
  });

  it("keeps bars thin and every chart on one axis (SPEC 11.3)", async () => {
    renderDashboard();
    await screen.findByRole("region", { name: "按集汇总" });
    await screen.findByRole("region", { name: "每个镜头花了多少时间和钱" });
    await screen.findByRole("region", { name: "各 API 的调用和花费" });
    await screen.findByRole("region", { name: "自动质检" });
    const bars = document.querySelectorAll<HTMLElement>("[data-hbar] [data-segment]");
    expect(bars.length).toBeGreaterThan(30);
    for (const b of bars) expect(parseFloat(b.style.height)).toBeLessThanOrEqual(24);
    for (const name of ["每个镜头花了多少时间和钱", "各组件累计计算时长（分钟）"]) {
      // Two or more series → a legend.
      expect(within(card(name)).getAllByRole("list")[0]).toBeInTheDocument();
    }
  });

  it("exports the calls as CSV", async () => {
    const created: Blob[] = [];
    const { createObjectURL, revokeObjectURL } = URL;
    URL.createObjectURL = (b: Blob) => {
      created.push(b);
      return "blob:calls";
    };
    URL.revokeObjectURL = () => undefined;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderAt(
      <>
        <Routes>
          <Route path="/s/:series/dashboard" element={<DashboardPage />} />
        </Routes>
        <Toaster />
      </>,
      "/s/demo/dashboard",
    );
    await screen.findByRole("region", { name: "预算" });
    await userEvent.click(screen.getByRole("button", { name: "导出 CSV" }));
    expect(await screen.findByText(/已导出 calls\.csv/)).toBeInTheDocument();
    expect(click).toHaveBeenCalled();
    const lines = (await (created[0] ?? new Blob()).text()).trim().split("\n");
    expect(lines[0]).toBe("time,kind,shot,model,where,duration_s,usage,cost_usd,result");
    expect(lines).toHaveLength(43);
    expect(lines.filter((l) => l.endsWith(",rate_limited"))).toHaveLength(1);
    click.mockRestore();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
  });
});
