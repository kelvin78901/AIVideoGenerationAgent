import {
  QueryClient,
  type InvalidateOptions,
  type InvalidateQueryFilters,
  type QueryKey,
} from "@tanstack/react-query";

/**
 * `invalidateQueries` also restarts a first fetch that is still in flight. TanStack cancels a
 * running fetch and starts over only when the query already has data; without data it attaches
 * the invalidation to the running fetch. That fetch may have read the state from before the
 * change, so the query ended up with old data and nothing left to refetch it (M6 step 10b:
 * 采纳 while the take list's first fetch was running left the shot's pill at 待挑选).
 */
class FreshQueryClient extends QueryClient {
  override invalidateQueries<TTaggedQueryKey extends QueryKey = QueryKey>(
    filters?: InvalidateQueryFilters<TTaggedQueryKey>,
    options?: InvalidateOptions,
  ): Promise<void> {
    if (filters?.refetchType !== "none" && options?.cancelRefetch !== false) {
      for (const query of this.getQueryCache().findAll(filters)) {
        const { data, fetchStatus } = query.state;
        // Silent: the fetch started next takes over its promise (what refetch does with data).
        if (data === undefined && fetchStatus === "fetching") void query.cancel({ silent: true });
      }
    }
    return super.invalidateQueries(filters, options);
  }
}

export function makeQueryClient(): QueryClient {
  return new FreshQueryClient({
    defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
  });
}
