import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { Job } from "@/api/schemas/jobs";
import { ConfirmJobs } from "@/components/ConfirmJobs";
import { server } from "@/mocks/node";
import { backend } from "@/test/backend";
import { renderAt } from "@/test/render";

function waitingJob(confirm: Record<string, unknown>, over: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    series_id: "demo",
    episode_id: null,
    product_id: "p-1",
    component_id: "script",
    kind: "product.run",
    queue: "api:deepseek",
    state: "waiting_confirm",
    priority: 0,
    attempt: 0,
    max_attempts: 3,
    params: { model_key: "deepseek/v4-pro", confirm },
    result: null,
    error: null,
    depends_on: [],
    est_cost_usd: 0.92,
    confirmed_usd: null,
    fallback_from_job_id: null,
    created_at: "2026-10-19T02:00:00Z",
    started_at: null,
    finished_at: null,
    ...over,
  };
}

/** Serves one waiting job; records which action was posted for it. */
function serve(job: Job) {
  const posted: string[] = [];
  let current = job;
  server.use(
    http.get("*/api/v1/jobs", () => HttpResponse.json([current])),
    http.post("*/api/v1/jobs/:id/:action", ({ params }) => {
      posted.push(String(params.action));
      current = { ...current, state: params.action === "confirm" ? "queued" : "canceled" };
      return HttpResponse.json(current);
    }),
  );
  return posted;
}

beforeEach(() => backend());

describe("ConfirmJobs", () => {
  it("asks before a run over the per-call cap and queues it on a yes", async () => {
    const user = userEvent.setup();
    const posted = serve(waitingJob({ reason: "per_call", estimate_usd: 0.92, limit_usd: 0.8 }));
    renderAt(<ConfirmJobs />);
    expect(
      await screen.findByRole("dialog", { name: "「剧本化」要你点头才会开始" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("用 DeepSeek V4 Pro 预计 $0.92，超过了这一步的单次上限 $0.80。"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认，开始运行（$0.92）" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posted).toEqual(["confirm"]);
  });

  it("cancel drops the waiting run", async () => {
    const user = userEvent.setup();
    const posted = serve(
      waitingJob(
        {
          reason: "fallback",
          estimate_usd: 0.0042,
          limit_usd: null,
          failed_model: "deepseek/v4-pro",
          error: "rate_limited",
        },
        { params: { model_key: "qwen/qwen3.8-max" } },
      ),
    );
    renderAt(<ConfirmJobs />);
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "取消这次运行" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posted).toEqual(["cancel"]);
  });

  it("shows the fallback reason and small estimates with their digits", async () => {
    serve(
      waitingJob(
        {},
        {
          params: {
            model_key: "qwen/qwen3.8-max",
            confirm: {
              reason: "fallback",
              estimate_usd: 0.0042,
              limit_usd: null,
              failed_model: "deepseek/v4-pro",
              error: "rate_limited",
            },
          },
        },
      ),
    );
    renderAt(<ConfirmJobs />);
    expect(
      await screen.findByText(
        "DeepSeek V4 Pro 出错了（rate_limited）。要改用 Qwen3.8-max 吗？预计 $0.0042。",
      ),
    ).toBeInTheDocument();
  });

  it("says when the model has no price instead of showing $0", async () => {
    serve(waitingJob({ reason: "unpriced", estimate_usd: 0, limit_usd: null }));
    renderAt(<ConfirmJobs />);
    expect(
      await screen.findByText(
        "DeepSeek V4 Pro 没有单价，这次花多少不知道。可以在模型页给它填上单价。",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认，开始运行（价格未知）" })).toBeInTheDocument();
  });

  it("names the shot's cap when a shot would pass it", async () => {
    serve(waitingJob({ reason: "shot", estimate_usd: 0.92, limit_usd: 0.4 }));
    renderAt(<ConfirmJobs />);
    expect(
      await screen.findByText("用 DeepSeek V4 Pro 预计 $0.92，这个镜头离单镜上限只剩 $0.40。"),
    ).toBeInTheDocument();
  });

  it("shows nothing when no run is waiting", async () => {
    renderAt(<ConfirmJobs />);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
