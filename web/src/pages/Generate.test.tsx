import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { getDb } from "@/mocks/db";
import { demoTiming } from "@/mocks/events";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { DEMO_SERIES_ID } from "@/mocks/fixtures/demo/series";
import GeneratePage from "@/pages/Generate";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

function Page() {
  useEventStream();
  return (
    <>
      <GeneratePage />
      <Toaster />
    </>
  );
}

function renderGenerate(path = "/s/demo/e/1/generate") {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/generate" element={<Page />} />
    </Routes>,
    path,
  );
}

const video = (label: string) => getDb().products[`demo-p-vid-${label}`];
const pills = () => screen.getByRole("region", { name: "镜头" });
const pill = (label: string) =>
  within(pills()).getByRole("button", { name: new RegExp(`^${label}`) });
const wall = () => screen.getByRole("list", { name: "候选" });
const take = (n: number) => within(wall()).getByRole("listitem", { name: `候选 T${n}` });
const ready = () => screen.findByRole("heading", { name: "镜头 1-04 的候选" });

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  demoTiming.runMs = 20;
});
afterEach(() => {
  vi.unstubAllGlobals();
  demoTiming.runMs = 1400;
});

describe("GeneratePage", () => {
  it("shows the queues, QA tallies and the 9 shots; opens on 1-04 with 4 takes", async () => {
    renderGenerate();
    await ready();
    const cards = screen.getByRole("region", { name: "队列和质检" });
    expect(within(cards).getByText("通过 6 · 未过 4")).toBeInTheDocument();
    expect(within(cards).getByText(/已自动重跑 1 次 · 自动兜底 1 次/)).toBeInTheDocument();
    expect(await within(cards).findByText("空闲 · 本集已花 $8.94")).toBeInTheDocument();
    expect(await within(cards).findByText("单镜上限 $2，超了会先问你")).toBeInTheDocument();
    expect(within(cards).getByText("正在跑 1-05 T1（MiniMax H3（本地））")).toBeInTheDocument();
    expect(within(pills()).getAllByRole("button")).toHaveLength(9);
    expect(pill("1-01")).toHaveTextContent("已采纳");
    expect(pill("1-04")).toHaveTextContent("待挑选");
    expect(pill("1-05")).toHaveTextContent("生成中");
    expect(pill("1-06")).toHaveTextContent("排队");
    expect(pill("1-08")).toHaveTextContent("等待");
    expect(within(wall()).getAllByRole("listitem")).toHaveLength(4);
    expect(await screen.findByText("当前产物 · 镜头 1-04 视频候选")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /再出一条/ })).toBeInTheDocument();
  });

  it("shows each take's QA, the reason it exists, and recommends T3", async () => {
    renderGenerate();
    await ready();
    const t1 = take(1);
    expect(t1).toHaveTextContent("未过 2 项");
    expect(t1).toHaveTextContent("0.71");
    expect(t1).toHaveTextContent("手指粘连");
    expect(t1).toHaveTextContent("质检没过，已自动重跑");
    expect(take(2)).toHaveTextContent("自动重跑");
    expect(take(3)).toHaveTextContent("本地超时，自动兜底到 API");
    expect(take(3)).toHaveTextContent("$0.32");
    expect(take(4)).toHaveTextContent("不满意换一个");
    expect(take(4)).toHaveTextContent("$1.64");
    expect(take(4)).toHaveTextContent("声控灯没有闪");
    expect(within(take(3)).getByText("推荐")).toBeInTheDocument();
    expect(within(take(2)).queryByText("推荐")).toBeNull();
    // Picks 1-01 to see an adopted take: no recommendation once one is adopted.
    const user = userEvent.setup();
    await user.click(pill("1-01"));
    expect(within(take(2)).getByText("已采纳")).toBeInTheDocument();
    expect(take(2)).toHaveTextContent("混合模式出终版");
    expect(screen.queryByText("推荐")).toBeNull();
  });

  it("adopts one take per shot, then un-adopts; 生成 goes to 4 / 9", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(within(take(3)).getByRole("button", { name: "采纳" }));
    await waitFor(() => expect(video("1-04")?.adopted_version_id).toBe("demo-p-vid-1-04-v3"));
    expect(await screen.findByText("1-04 采纳 T3。")).toBeInTheDocument();
    await waitFor(() => expect(pill("1-04")).toHaveTextContent("已采纳"));
    const res = await fetch(`http://localhost/api/v1/episodes/${EP1}/progress`);
    const body = (await res.json()) as { steps: { generate: { done: number } } };
    expect(body.steps.generate.done).toBe(4);

    await user.click(within(take(4)).getByRole("button", { name: "采纳" }));
    expect(await screen.findByText(/注意：有 1 项质检没过，你选择了保留/)).toBeInTheDocument();
    await waitFor(() => expect(video("1-04")?.adopted_version_id).toBe("demo-p-vid-1-04-v4"));
    await waitFor(() => expect(within(take(4)).getByText("已采纳")).toBeInTheDocument());
    expect(within(take(3)).queryByText("已采纳")).toBeNull();

    await user.click(within(take(4)).getByRole("button", { name: "取消采纳" }));
    await waitFor(() => expect(video("1-04")?.adopted_version_id).toBeNull());
    expect(await screen.findByText("已取消采纳 1-04 T4。")).toBeInTheDocument();
  });

  it("explains shots without takes: generating, queued, waiting for a tail frame", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(pill("1-05"));
    expect(
      screen.getByText("MiniMax H3（本地） 正在出第 1 条候选。出来后会自动质检，然后出现在这里。"),
    ).toBeInTheDocument();
    await user.click(pill("1-06"));
    expect(
      screen.getByText("排在本地队列第 1 位。台词会先用锁定音色配好，再生成画面。"),
    ).toBeInTheDocument();
    await user.click(pill("1-07"));
    expect(
      await screen.findByText("排在本地队列第 2 位。画面文字后期贴，所以这里只出无字画面。"),
    ).toBeInTheDocument();
    await user.click(pill("1-08"));
    expect(
      screen.getByText("等 1-06 采纳：这个镜头的首帧要用 1-06 的最后一帧。"),
    ).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /再出一条/ }));
    expect(
      await screen.findByText("等 1-06 采纳：这个镜头的首帧要用 1-06 的最后一帧"),
    ).toBeInTheDocument();
  });

  it("adopting the shot a waiting shot continues unblocks it", async () => {
    // Give 1-06 a finished take so it can be adopted.
    const p = video("1-06");
    const src = video("1-04")?.versions[2];
    if (!p || !src) throw new Error("fixtures");
    p.versions = [{ ...src, id: "demo-p-vid-1-06-v1", product_id: p.id, n: 1 }];
    p.current_version_id = "demo-p-vid-1-06-v1";
    p.status = "ready";
    p.running = null;
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(pill("1-06"));
    await user.click(within(take(1)).getByRole("button", { name: "采纳" }));
    expect(await screen.findByText("1-06 采纳 T1。1-08 现在可以开始生成了。")).toBeInTheDocument();
    await waitFor(() => expect(pill("1-08")).toHaveTextContent("未开始"));
  });

  it("「再出一条」 adds a take with QA and a run-log line", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(await screen.findByRole("button", { name: /再出一条/ }));
    const t5 = await within(wall()).findByRole("listitem", { name: "候选 T5" });
    expect(t5).toHaveTextContent("MiniMax H3（本地）");
    expect(t5).toHaveTextContent("通过");
    const log = screen.getByRole("region", { name: "运行记录" });
    expect(await within(log).findByText("MiniMax H3（本地） 出 T5 · 质检通过")).toBeInTheDocument();
    expect(within(log).getAllByRole("listitem")[0]).toHaveTextContent("1-04");
  });

  it("keyboard: ← → move, 1–5 rate, A adopts, Space plays", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    expect(take(3)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowRight}");
    expect(take(4)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(take(2)).toHaveAttribute("aria-current", "true");
    await user.keyboard("4");
    await waitFor(() => expect(video("1-04")?.versions[1]?.rating).toBe(4));
    expect(await within(take(2)).findByText("4 分")).toBeInTheDocument();
    await user.keyboard("a");
    await waitFor(() => expect(video("1-04")?.adopted_version_id).toBe("demo-p-vid-1-04-v2"));
    await user.keyboard(" ");
    expect(await screen.findByText(/播放 1-04 T2/)).toBeInTheDocument();
  });

  it("sends a take to 2K finishing on the configured route", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(await within(take(3)).findByRole("button", { name: "2K 精修 · 本地" }));
    expect(
      await screen.findByText("已把 1-04 T3 送去 2K 精修（SeedVR2（本地）），本地跑，不计费。"),
    ).toBeInTheDocument();
  });

  it("saves the auto rules and shows the QA thresholds", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    const takesN = await screen.findByLabelText("每个镜头先出");
    expect(takesN).toHaveValue(3);
    await user.clear(takesN);
    await user.type(takesN, "4");
    await user.tab();
    await waitFor(() => expect(getDb().generateRules[DEMO_SERIES_ID]?.takes_per_shot).toBe(4));
    const cap = screen.getByLabelText("单个镜头花费超过 $");
    await user.clear(cap);
    await user.type(cap, "3{Enter}");
    await waitFor(() => expect(getDb().generateRules[DEMO_SERIES_ID]?.shot_cap_usd).toBe(3));
    expect(await screen.findByText("单镜上限 $3，超了会先问你")).toBeInTheDocument();
    expect(screen.getByText(/人脸一致性 ≥ 0.75.*错字率 ≤ 10%/)).toBeInTheDocument();
  });

  it("lists the run log newest first", async () => {
    renderGenerate();
    await ready();
    const log = screen.getByRole("region", { name: "运行记录" });
    const lines = await within(log).findAllByRole("listitem");
    expect(lines).toHaveLength(6);
    expect(lines[0]).toHaveTextContent("1-05开始生成 · MiniMax H3（本地）");
    expect(lines[2]).toHaveTextContent("MiniMax H3 API 出 T3 · $0.32 · 质检通过");
    expect(lines[3]).toHaveTextContent("本地任务超过 10 分钟 → 自动兜底到 MiniMax H3 API");
    expect(lines[5]).toHaveTextContent("未过 2 项（人脸、手指）→ 自动重跑");
  });

  it("opens on the shot in ?shot= (后期「换一条候选」)", async () => {
    renderGenerate("/s/demo/e/1/generate?shot=1-02");
    expect(await screen.findByRole("heading", { name: "镜头 1-02 的候选" })).toBeInTheDocument();
    expect(pill("1-02")).toHaveAttribute("aria-pressed", "true");
  });

  it("the run bar follows the Inspector: 2K 精修", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(screen.getByRole("button", { name: "2K 精修" }));
    expect(await screen.findByText("当前产物 · 2K 精修队列 · 3 条")).toBeInTheDocument();
  });
});
