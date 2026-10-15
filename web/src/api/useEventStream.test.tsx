import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";

import { callKeys, jobKeys } from "@/api/hooks/useJobs";
import { makeQueryClient } from "@/api/queryClient";
import type { Job } from "@/api/schemas/jobs";
import { useEventStream } from "@/api/useEventStream";
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
});
