import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { niceTicks } from "@/components/charts/scale";
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
