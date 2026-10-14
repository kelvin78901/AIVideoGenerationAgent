import { QueryClientProvider } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeQueryClient } from "@/api/queryClient";
import { LiveRoutes } from "@/app/App";
import { Toaster } from "@/components/ui/sonner";
import { useUiStore } from "@/stores/ui";
import { FakeEventSource } from "@/test/fakeEventSource";
import { makeCall, makeJob } from "@/test/fixtures";
import { renderAt } from "@/test/render";

const routes = new Map<string, () => unknown>();

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  act(() => useUiStore.setState({ lang: "zh-CN" }));
  routes.clear();
  routes.set("GET /api/v1/jobs?limit=200", () => []);
  routes.set("GET /api/v1/dev/model-calls?limit=200", () => []);
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const handler = routes.get(`${init?.method ?? "GET"} ${String(input)}`);
    return handler ? json(200, handler()) : json(404, { detail: { code: "nope", params: {} } });
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderPanel() {
  return renderAt(
    <QueryClientProvider client={makeQueryClient()}>
      <LiveRoutes />
      <Toaster />
    </QueryClientProvider>,
    "/dev/jobs",
  );
}

describe("/dev/jobs", () => {
  it("starts a mock LLM call and follows the job over SSE", async () => {
    const job = makeJob({ id: "j00000001" });
    routes.set("POST /api/v1/dev/llm-test", () => job);
    renderPanel();
    expect(
      await screen.findByRole("heading", { name: "开发 · 任务与调用记录" }),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "发起一次 Mock LLM 调用" }));
    const row = await screen.findByTestId("job-j00000001");
    expect(within(row).getByText("排队中")).toBeInTheDocument();

    const source = FakeEventSource.latest();
    act(() => source.emit("job.updated", { ...job, state: "running", attempt: 1 }, 1));
    // React Query notifies observers asynchronously, so wait for the re-render.
    await waitFor(() =>
      expect(within(screen.getByTestId("job-j00000001")).getByText("运行中")).toBeInTheDocument(),
    );

    routes.set("GET /api/v1/dev/model-calls?limit=200", () => [makeCall({ job_id: job.id })]);
    act(() => {
      source.emit(
        "job.updated",
        { ...job, state: "succeeded", attempt: 1, result: { model_key: "deepseek/v4-pro" } },
        2,
      );
      source.emit("cost.updated", { call_id: 1 }, 3);
    });
    await waitFor(() =>
      expect(within(screen.getByTestId("job-j00000001")).getByText("完成")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByTestId("calls-total")).toHaveTextContent("共 1 条，已计费 API 花费 $0.25"),
    );
    // the top bar's spend follows the same data
    expect(screen.getAllByText("$0.25").length).toBeGreaterThanOrEqual(1);
  });

  it("shows translated backend errors", async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: "发起一次 Mock LLM 调用" }));
    expect(await screen.findByText("出错了：nope")).toBeInTheDocument();
  });

  it("counts GPU jobs in the top bar", async () => {
    routes.set("GET /api/v1/jobs?limit=200", () => [
      makeJob({ id: "g1", queue: "gpu", state: "running" }),
      makeJob({ id: "g2", queue: "gpu", state: "queued" }),
      makeJob({ id: "a1", queue: "api:x", state: "running" }),
    ]);
    renderPanel();
    await waitFor(() =>
      expect(screen.getByTestId("gpu-status")).toHaveTextContent("本地 GPU：运行中 1 · 排队 1"),
    );
  });
});
