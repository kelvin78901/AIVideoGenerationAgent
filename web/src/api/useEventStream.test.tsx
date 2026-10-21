import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import { callKeys, jobKeys } from "@/api/hooks/useJobs";
import { makeQueryClient } from "@/api/queryClient";
import type { Job } from "@/api/schemas/jobs";
import { useEventStream } from "@/api/useEventStream";
import { Toaster } from "@/components/ui/sonner";
import "@/i18n";
import { FakeEventSource } from "@/test/fakeEventSource";
import { makeJob } from "@/test/fixtures";

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

function setup() {
  const client = makeQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useEventStream(), { wrapper });
  return { client, hook, source: FakeEventSource.latest() };
}

describe("useEventStream", () => {
  it("opens one stream on /api/v1/events and closes it on unmount", () => {
    const { hook, source } = setup();
    expect(source.url).toBe("/api/v1/events");
    hook.unmount();
    expect(source.closed).toBe(true);
  });

  it("upserts job.updated into the jobs cache", () => {
    const { client, source } = setup();
    const old = makeJob({ id: "old", created_at: "2026-10-14T09:00:00+00:00" });
    client.setQueryData<Job[]>(jobKeys.all, [old]);
    act(() => source.emit("job.updated", makeJob({ id: "new", state: "queued" }), 1));
    act(() => source.emit("job.updated", makeJob({ id: "new", state: "running" }), 2));
    const jobs = client.getQueryData<Job[]>(jobKeys.all);
    expect(jobs?.map((j) => [j.id, j.state])).toEqual([
      ["new", "running"],
      ["old", "queued"],
    ]);
  });

  it("refetches calls on cost.updated and everything on (re)connect", () => {
    const { client, source } = setup();
    const spy = vi.spyOn(client, "invalidateQueries");
    act(() => source.emit("cost.updated", { cost_usd: 0.1 }, 3));
    expect(spy).toHaveBeenCalledWith({ queryKey: callKeys.all });
    spy.mockClear();
    act(() => source.emit("open"));
    expect(spy).toHaveBeenCalledWith({ queryKey: jobKeys.all });
    expect(spy).toHaveBeenCalledWith({ queryKey: callKeys.all });
  });

  it("refetches products, the script status and the badges on gate.updated", () => {
    const { client, source } = setup();
    const spy = vi.spyOn(client, "invalidateQueries");
    act(() => source.emit("gate.updated", { gate: "novel", scope_id: "demo", action: "confirm" }));
    expect(spy).toHaveBeenCalledWith({ queryKey: ["products"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["series"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["episodes"] });
  });

  it("says how a 确认并同步 ended", async () => {
    render(<Toaster />);
    const { source } = setup();
    const done = (failed: number) => ({
      level: failed ? "warning" : "success",
      code: "cascade_done",
      params: { count: 3, failed },
    });
    act(() => source.emit("toast", done(0), 4));
    expect(
      await screen.findByText("已同步：3 个产物更新，新版本已采纳。旧版本都在历史里。"),
    ).toBeInTheDocument();
    act(() => source.emit("toast", done(1), 5));
    expect(await screen.findByText(/同步结束：3 个产物更新，1 个失败/)).toBeInTheDocument();
  });
});
