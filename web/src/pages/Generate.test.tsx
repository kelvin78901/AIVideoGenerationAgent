import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";

import type { Job } from "@/api/schemas/jobs";
import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { server } from "@/mocks/node";
import GeneratePage from "@/pages/Generate";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { confirmFakeStoryboard, fakeGenerate } from "@/test/fakes/generate";
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

const video = (label: string) => fakeGenerate.videos.find((p) => p.id === `demo-p-vid-${label}`);
const pills = () => screen.getByRole("region", { name: "镜头" });
const pill = (label: string) =>
  within(pills()).getByRole("button", { name: new RegExp(`^${label}`) });
const wall = () => screen.getByRole("list", { name: "候选" });
const take = (n: number) => within(wall()).getByRole("listitem", { name: `候选 T${n}` });
const ready = () => screen.findByRole("heading", { name: "镜头 1-04 的候选" });

/** A job of the queue page's list (`GET /jobs`). */
function job(id: string, state: Job["state"], queue: string, model: string, fallback = false): Job {
  return {
    id,
    series_id: "demo",
    product_id: `demo-p-vid-${id}`,
    component_id: "vid",
    kind: "product.run",
    queue,
    state,
    priority: 0,
    attempt: 0,
    max_attempts: 3,
    params: { mode: "run", model_key: model },
    result: null,
    error: null,
    depends_on: [],
    est_cost_usd: 0,
    fallback_from_job_id: fallback ? `local-${id}` : null,
    created_at: "2026-10-22T10:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
  // The seeded demo (studio/demo.py): 分镜 confirmed, episode 1's takes made.
  confirmFakeStoryboard();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("GeneratePage", () => {
  it("shows the queues and the 9 shots; opens on 1-04 with its 4 takes", async () => {
    renderGenerate();
    await ready();
    const cards = screen.getByRole("region", { name: "队列和质检" });
    // QA is M6: the takes are not checked yet.
    expect(within(cards).getByText("10 条候选还没质检")).toBeInTheDocument();
    expect(within(cards).getByText(/已自动重跑 0 次 · 自动兜底 1 次/)).toBeInTheDocument();
    expect(await within(cards).findByText("空闲 · 本集已花 $8.94")).toBeInTheDocument();
    expect(await within(cards).findByText("单镜上限 $2，超了会先问你")).toBeInTheDocument();
    expect(within(cards).getByText("没有镜头在生成")).toBeInTheDocument();
    expect(within(pills()).getAllByRole("button")).toHaveLength(9);
    expect(pill("1-01")).toHaveTextContent("已采纳");
    expect(pill("1-04")).toHaveTextContent("待挑选");
    expect(pill("1-05")).toHaveTextContent("未开始");
    expect(pill("1-08")).toHaveTextContent("等待");
    expect(within(wall()).getAllByRole("listitem")).toHaveLength(4);
    expect(await screen.findByText("当前产物 · 镜头 1-04 视频候选")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /再出一条/ })).toBeInTheDocument();
  });

  it("groups the queues by model, with what fell back to the API and what waits for a yes", async () => {
    server.use(
      http.get("*/api/v1/jobs", () =>
        HttpResponse.json([
          job("1-05", "running", "gpu", "comfy/h3"),
          job("1-06", "queued", "gpu", "comfy/h3"),
          job("1-07", "queued", "gpu", "comfy/h3-r2v"),
          job("1-02", "running", "api:minimax", "minimax/h3-api", true),
          job("1-03", "waiting_confirm", "api:volc", "volc/seedance-2.5"),
        ]),
      ),
    );
    renderGenerate();
    await ready();
    const cards = screen.getByRole("region", { name: "队列和质检" });
    expect(await within(cards).findByText("运行中 1 · 排队 2")).toBeInTheDocument();
    expect(within(cards).getByText("MiniMax H3（本地）：运行 1 · 排队 1")).toBeInTheDocument();
    expect(
      within(cards).getByText("MiniMax H3 参考生视频（本地）：运行 0 · 排队 1"),
    ).toBeInTheDocument();
    expect(within(cards).getByText("MiniMax H3 API：运行 1 · 排队 0")).toBeInTheDocument();
    expect(within(cards).getByText("1 个本地任务已兜底到 API")).toBeInTheDocument();
    expect(within(cards).getByText("1 个任务等你确认花费")).toBeInTheDocument();
  });

  it("shows each take's first frame, model, cost and why it exists", async () => {
    renderGenerate();
    await ready();
    const t1 = take(1);
    expect(t1).toHaveTextContent("MiniMax H3 参考生视频（本地）");
    expect(t1).toHaveTextContent("未检查");
    const poster = within(t1).getByRole("img", { name: "候选 T1 的第一帧" });
    expect(poster.getAttribute("src")).toMatch(/\/api\/v1\/files\/[0-9a-f]{64}$/);
    expect(take(3)).toHaveTextContent("本地超时，自动兜底到 API");
    expect(take(3)).toHaveTextContent("MiniMax H3 API");
    expect(take(3)).toHaveTextContent("$0.51");
    expect(take(4)).toHaveTextContent("不满意换一个");
    expect(take(4)).toHaveTextContent("$2.37");
    // No QA, no recommendation yet (「推荐」 goes by the QA score).
    expect(screen.queryByText("推荐")).toBeNull();
    const user = userEvent.setup();
    await user.click(pill("1-01"));
    expect(within(take(2)).getByText("已采纳")).toBeInTheDocument();
    expect(take(2)).toHaveTextContent("混合模式出终版");
    expect(take(2)).toHaveTextContent("H3 Regenerate-2K");
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
    await waitFor(() => expect(video("1-04")?.adopted_version_id).toBe("demo-p-vid-1-04-v4"));
    await waitFor(() => expect(within(take(4)).getByText("已采纳")).toBeInTheDocument());
    expect(within(take(3)).queryByText("已采纳")).toBeNull();

    await user.click(within(take(4)).getByRole("button", { name: "取消采纳" }));
    await waitFor(() => expect(video("1-04")?.adopted_version_id).toBeNull());
    expect(await screen.findByText("已取消采纳 1-04 T4。")).toBeInTheDocument();
  });

  it("explains shots without takes; a shot waiting for a tail frame cannot run yet", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(pill("1-05"));
    expect(screen.getByText("还没有候选。点「再出一条」开始生成。")).toBeInTheDocument();
    await user.click(pill("1-08"));
    expect(
      screen.getByText("等 1-06 采纳：这个镜头的首帧要用 1-06 的最后一帧。"),
    ).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /再出一条/ }));
    expect(
      await screen.findByText("等 1-06 采纳：这个镜头的首帧要用 1-06 的最后一帧"),
    ).toBeInTheDocument();
    expect(fakeGenerate.runs).toEqual([]);
  });

  it("a first run makes the rule's takes; adopting one unblocks the shot that continues it", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(pill("1-06"));
    await user.click(await screen.findByRole("button", { name: /再出一条/ }));
    // 每个镜头先出 2 条 (the auto rules).
    await within(wall()).findByRole("listitem", { name: "候选 T2" });
    expect(within(wall()).getAllByRole("listitem")).toHaveLength(2);
    expect(take(1)).toHaveTextContent("MiniMax H3（本地）");
    await user.click(within(take(1)).getByRole("button", { name: "采纳" }));
    expect(await screen.findByText("1-06 采纳 T1。1-08 现在可以开始生成了。")).toBeInTheDocument();
    await waitFor(() => expect(pill("1-08")).toHaveTextContent("未开始"));
  });

  it("「再出一条」 adds one take and a run-log line", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(await screen.findByRole("button", { name: /再出一条/ }));
    const t5 = await within(wall()).findByRole("listitem", { name: "候选 T5" });
    expect(t5).toHaveTextContent("MiniMax H3（本地）");
    expect(fakeGenerate.runs.map((r) => [r.id, r.mode])).toEqual([["demo-p-vid-1-04", "rerun"]]);
    const log = screen.getByRole("region", { name: "运行记录" });
    expect(await within(log).findByText("MiniMax H3（本地） 出 T5")).toBeInTheDocument();
    expect(within(log).getAllByRole("listitem")[0]).toHaveTextContent("1-04");
  });

  it("keyboard: ← → move, 1–5 rate, A adopts, Space plays", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    // Nothing adopted and no QA to recommend by: the newest take.
    expect(take(4)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowLeft}");
    expect(take(3)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowLeft}");
    expect(take(2)).toHaveAttribute("aria-current", "true");
    await user.keyboard("4");
    await waitFor(() => expect(video("1-04")?.versions[1]?.rating).toBe(4));
    expect(await within(take(2)).findByText("4 分")).toBeInTheDocument();
    await user.keyboard("a");
    await waitFor(() => expect(video("1-04")?.adopted_version_id).toBe("demo-p-vid-1-04-v2"));
    // Space plays the take in the lightbox: the backend's clip, with its first frame.
    await user.keyboard(" ");
    const player = await screen.findByRole("dialog", { name: /^1-04 T2 · / });
    const clip = within(player).getByLabelText(/^1-04 T2 · /);
    expect(clip.tagName).toBe("VIDEO");
    expect(clip.getAttribute("src")).toMatch(/\/api\/v1\/files\/[0-9a-f]{64}$/);
    expect(clip.getAttribute("poster")).toMatch(/\/api\/v1\/files\/[0-9a-f]{64}$/);
  });

  it("「用 API 出终版」 regenerates a local H3 draft at 2K", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    // Only the local drafts can be regenerated (T3 is the H3 API's, T4 Seedance's).
    expect(within(take(3)).queryByRole("button", { name: /用 API 出终版/ })).toBeNull();
    expect(within(take(4)).queryByRole("button", { name: /用 API 出终版/ })).toBeNull();
    await user.click(within(take(1)).getByRole("button", { name: "用 API 出终版 · 约 $0.19" }));
    expect(await screen.findByText("已开始出 1-04 T1 的 2K 终版（API）。")).toBeInTheDocument();
    expect(fakeGenerate.runs).toEqual([
      {
        id: "demo-p-vid-1-04",
        mode: "run",
        where: "api",
        params: { source_version_id: "demo-p-vid-1-04-v1" },
      },
    ]);
    const t5 = await within(wall()).findByRole("listitem", { name: "候选 T5" });
    expect(t5).toHaveTextContent("H3 Regenerate-2K");
    expect(t5).toHaveTextContent("混合模式出终版");
    expect(t5).toHaveTextContent("2k");
  });

  it("the play button opens the take in the lightbox", async () => {
    const user = userEvent.setup();
    renderGenerate();
    await ready();
    await user.click(within(take(3)).getByRole("button", { name: "播放 T3" }));
    expect(
      await screen.findByRole("dialog", { name: "1-04 T3 · MiniMax H3 API" }),
    ).toBeInTheDocument();
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
    expect(takesN).toHaveValue(2);
    await user.clear(takesN);
    await user.type(takesN, "4");
    await user.tab();
    await waitFor(() => expect(fakeGenerate.rules.takes_per_shot).toBe(4));
    const cap = screen.getByLabelText("单个镜头花费超过 $");
    await user.clear(cap);
    await user.type(cap, "3{Enter}");
    await waitFor(() => expect(fakeGenerate.rules.shot_cap_usd).toBe(3));
    expect(await screen.findByText("单镜上限 $3，超了会先问你")).toBeInTheDocument();
    expect(screen.getByText(/人脸一致性 ≥ 0.75.*错字率 ≤ 10%/)).toBeInTheDocument();
  });

  it("lists the run log newest first", async () => {
    renderGenerate();
    await ready();
    const log = screen.getByRole("region", { name: "运行记录" });
    const lines = await within(log).findAllByRole("listitem");
    expect(lines).toHaveLength(11);
    expect(lines[0]).toHaveTextContent("1-04你点了「不满意换一个」→ Seedance 2.5 出 T4 · $2.37");
    expect(lines[1]).toHaveTextContent("MiniMax H3 API 出 T3 · $0.51");
    expect(lines[2]).toHaveTextContent("本地任务超过 10 分钟 → 自动兜底到 MiniMax H3 API");
    expect(lines[5]).toHaveTextContent("1-03用 API 出终版 → H3 Regenerate-2K 出 T2 · $0.25");
    expect(lines[10]).toHaveTextContent("1-01MiniMax H3（本地） 出 T1");
  });

  it("opens on the shot in ?shot= (后期「换一条候选」)", async () => {
    renderGenerate("/s/demo/e/1/generate?shot=demo-shot-1-02");
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

describe("GeneratePage before 分镜确认", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", FakeEventSource);
    backend();
  });

  it("a run is refused until the storyboard is confirmed", async () => {
    const user = userEvent.setup();
    renderGenerate("/s/demo/e/1/generate?shot=demo-shot-1-05");
    expect(await screen.findByRole("heading", { name: "镜头 1-05 的候选" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /再出一条/ }));
    expect(await screen.findByText("分镜还没确认：确认分镜后才能出视频")).toBeInTheDocument();
  });
});
