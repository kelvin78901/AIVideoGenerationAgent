import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { makeQueryClient } from "@/api/queryClient";

/** A query whose first fetch read the state before a change and answers after it. */
async function invalidatedDuringFirstFetch(client: QueryClient): Promise<unknown> {
  let release: (value: string) => void = () => {};
  let calls = 0;
  const observer = new QueryObserver(client, {
    queryKey: ["products", "list"],
    queryFn: () => {
      calls += 1;
      return calls === 1
        ? new Promise<string>((resolve) => (release = resolve))
        : Promise.resolve("adopted");
    },
    retry: false,
  });
  const unsubscribe = observer.subscribe(() => {});
  await Promise.resolve();
  const done = client.invalidateQueries({ queryKey: ["products"] });
  release("before adopt");
  await done;
  await new Promise((resolve) => setTimeout(resolve, 0));
  unsubscribe();
  return client.getQueryData(["products", "list"]);
}

describe("makeQueryClient", () => {
  it("refetches a query invalidated while its first fetch is running", async () => {
    expect(await invalidatedDuringFirstFetch(makeQueryClient())).toBe("adopted");
  });

  it("is needed: a plain client keeps what the first fetch read", async () => {
    expect(await invalidatedDuringFirstFetch(new QueryClient())).toBe("before adopt");
  });
});
