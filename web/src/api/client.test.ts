import { z } from "zod";

import i18n from "@/i18n";
import { useDemoStore } from "@/stores/demo";

import { api, ApiError, errorMessage, post } from "./client";

const Ok = z.object({ ok: z.boolean() });

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      new Response(body === undefined ? "" : JSON.stringify(body), { status, headers }),
    );
}

afterEach(() => {
  vi.restoreAllMocks();
  void i18n.changeLanguage("zh-CN");
});

describe("api client", () => {
  it("prefixes /api/v1 and parses JSON against the schema", async () => {
    const spy = mockFetch(200, { ok: true, extra: 1 });
    await expect(api("/health", Ok)).resolves.toEqual({ ok: true });
    expect(spy.mock.calls[0]?.[0]).toBe("/api/v1/health");
    expect(spy.mock.calls[0]?.[1]?.headers).toMatchObject({ "X-Drama-Studio": "1" });
  });

  it("sends JSON bodies with post", async () => {
    const spy = mockFetch(200, {});
    await post("/dev/llm-test", z.object({}), { delay_s: 1 });
    expect(spy.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ delay_s: 1 }),
    });
  });

  it("rejects responses that break the contract with bad_response", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockFetch(200, { ok: "yes" });
    const err = await api("/health", Ok).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "bad_response", params: { path: "/health" } });
    expect((err as ApiError).params.issues).toContain("ok");
    expect(errorMessage(i18n.t, err)).toBe("接口返回的数据和约定不符：/health");
  });

  it("turns error bodies into ApiError with code and params", async () => {
    mockFetch(404, { detail: { code: "job_not_found", params: { id: "x1" } } });
    const err = await api("/jobs/x1", Ok).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "job_not_found", params: { id: "x1" } });
    expect(errorMessage(i18n.t, err)).toBe("找不到任务 x1");
    await i18n.changeLanguage("en");
    expect(errorMessage(i18n.t, err)).toBe("Job x1 not found");
  });

  it("falls back for unknown codes and non-JSON errors", async () => {
    mockFetch(500, { detail: "boom" });
    const err = await api("/x", Ok).catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "http_500" });
    expect(errorMessage(i18n.t, err)).toBe("出错了：http_500");
  });

  it("reports network failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = await api("/x", Ok).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 0, code: "network" });
    expect(errorMessage(i18n.t, err)).toContain("连不上后端");
  });

  it("marks the current route when a response carries the demo header", async () => {
    useDemoStore.getState().setRoute("/s/demo/spec");
    mockFetch(200, { ok: true });
    await api("/real", Ok);
    expect(useDemoStore.getState().routes).toEqual({});
    mockFetch(200, { ok: true }, { "x-drama-demo": "1" });
    await api("/demo", Ok);
    expect(useDemoStore.getState().routes).toEqual({ "/s/demo/spec": true });
  });
});
