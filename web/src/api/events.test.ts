import { QueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";

import { dispatchEvent } from "@/api/events";

const t = ((key: string) => key) as unknown as TFunction;

function invalidated(type: "product.updated" | "version.created", data: unknown) {
  const client = new QueryClient();
  const spy = vi.spyOn(client, "invalidateQueries").mockResolvedValue();
  dispatchEvent(client, t, type, data);
  return spy.mock.calls.map(([filters]) => filters?.queryKey);
}

describe("dispatchEvent", () => {
  it("says why a run failed in words", () => {
    const error = vi.spyOn(toast, "error").mockReturnValue(1);
    const words = ((key: string, opts?: Record<string, unknown>) => {
      if (key === "modelError.auth_failed") return "密钥不对";
      if (key === "toast.run_failed") return `失败：${String(opts?.error)}`;
      return String(opts?.defaultValue ?? key);
    }) as unknown as TFunction;
    const client = new QueryClient();
    const ev = (code: string) => ({ level: "error", code: "run_failed", params: { error: code } });
    dispatchEvent(client, words, "toast", ev("auth_failed"));
    dispatchEvent(client, words, "toast", ev("something_new"));
    expect(error.mock.calls.map(([text]) => text)).toEqual([
      "失败：密钥不对",
      "失败：something_new",
    ]);
    error.mockRestore();
  });

  it("refreshes product views when a product changes", () => {
    expect(invalidated("product.updated", { product_id: "p1", slot: "script" })).toEqual([
      ["products"],
      ["series"],
      ["episodes"],
    ]);
  });

  it("refreshes only the dubbing when a line's audio changes", () => {
    expect(invalidated("product.updated", { product_id: "p2", slot: "line_audio" })).toEqual([
      ["dub"],
    ]);
    expect(invalidated("version.created", { product_id: "p2", slot: "line_audio" })).toEqual([
      ["dub"],
    ]);
  });
});
