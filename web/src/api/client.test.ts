import i18n from "@/i18n";

import { api, ApiError, errorMessage, post } from "./client";

function mockFetch(status: number, body: unknown) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(body === undefined ? "" : JSON.stringify(body), { status }));
}

afterEach(() => {
  vi.restoreAllMocks();
  void i18n.changeLanguage("zh-CN");
});

describe("api client", () => {
  it("prefixes /api/v1 and parses JSON", async () => {
    const spy = mockFetch(200, { ok: true });
    await expect(api("/health")).resolves.toEqual({ ok: true });
    expect(spy.mock.calls[0]?.[0]).toBe("/api/v1/health");
    expect(spy.mock.calls[0]?.[1]?.headers).toMatchObject({ "X-Drama-Studio": "1" });
  });

  it("sends JSON bodies with post", async () => {
    const spy = mockFetch(200, {});
    await post("/dev/llm-test", { delay_s: 1 });
    expect(spy.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ delay_s: 1 }),
    });
  });

  it("turns error bodies into ApiError with code and params", async () => {
    mockFetch(404, { detail: { code: "job_not_found", params: { id: "x1" } } });
    const err = await api("/jobs/x1").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "job_not_found", params: { id: "x1" } });
    expect(errorMessage(i18n.t, err)).toBe("找不到任务 x1");
    await i18n.changeLanguage("en");
    expect(errorMessage(i18n.t, err)).toBe("Job x1 not found");
  });

  it("falls back for unknown codes and non-JSON errors", async () => {
    mockFetch(500, { detail: "boom" });
    const err = await api("/x").catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "http_500" });
    expect(errorMessage(i18n.t, err)).toBe("出错了：http_500");
  });

  it("reports network failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = await api("/x").catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 0, code: "network" });
    expect(errorMessage(i18n.t, err)).toContain("连不上后端");
  });
});
