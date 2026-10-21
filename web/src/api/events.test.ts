import { QueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
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
