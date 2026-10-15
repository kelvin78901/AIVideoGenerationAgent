import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

import { api } from "@/api/client";
import { onEvent } from "@/api/events";
import { useEpisodes } from "@/api/hooks/series";
import { HealthSchema } from "@/api/schemas/jobs";
import { useEventStream } from "@/api/useEventStream";
import { emitDemoEvent } from "@/mocks/events";
import { server } from "@/mocks/node";
import { useDemoStore } from "@/stores/demo";
import { FakeEventSource } from "@/test/fakeEventSource";
import { makeTestQueryClient } from "@/test/render";

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={makeTestQueryClient()}>{children}</QueryClientProvider>;
}

describe("demo data (MSW)", () => {
  it("answers unimplemented endpoints with demo data and the demo header", async () => {
    useDemoStore.getState().setRoute("/s/demo/e/1/novel");
    const { result } = renderHook(() => useEpisodes("demo"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0]?.title).toBe("红伞");
    expect(useDemoStore.getState().routes["/s/demo/e/1/novel"]).toBe(true);
  });

  it("returns translated errors for unknown ids", async () => {
    const { result } = renderHook(() => useEpisodes("nope"), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 404, code: "series_not_found" });
  });

  it("lets implemented endpoints through to the backend", async () => {
    // Stand-in for the real backend: a handler added by the test, without the demo header.
    server.use(
      http.get("*/api/v1/health", () =>
        HttpResponse.json({ status: "ok", version: "0.1.0", mock: true }),
      ),
    );
    useDemoStore.getState().setRoute("/dev/jobs");
    await expect(api("/health", HealthSchema)).resolves.toMatchObject({ mock: true });
    expect(useDemoStore.getState().routes).toEqual({});
  });

  it("delivers demo events through the same dispatcher as SSE", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const seen = vi.fn();
    const stop = onEvent("setup.log", seen);
    const { unmount } = renderHook(() => useEventStream(), { wrapper });
    emitDemoEvent("setup.log", { line: "ok" });
    expect(seen).toHaveBeenCalledWith({ line: "ok" });
    unmount();
    emitDemoEvent("setup.log", { line: "after" });
    expect(seen).toHaveBeenCalledTimes(1);
    stop();
    vi.unstubAllGlobals();
  });
});
