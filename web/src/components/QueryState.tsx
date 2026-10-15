import { useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { AlertCircle, CircleSlash } from "lucide-react";
import { useCallback, useSyncExternalStore, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { errorMessage } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Grey blocks while data loads. `data-loading` tells Playwright the page is not ready yet. */
export function Skeleton({ className }: { className?: string }) {
  const { t } = useTranslation("components");
  return (
    <div
      data-loading
      role="status"
      aria-label={t("query.loading")}
      className={cn("animate-pulse rounded-md bg-muted", className)}
    />
  );
}

/** Translated error with a retry button. */
export function QueryError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const { t: tc } = useTranslation("components");
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-2 rounded-md border border-tone-fail-border bg-tone-fail-bg px-3 py-2 text-sm text-tone-fail-fg"
    >
      <AlertCircle className="size-4" aria-hidden />
      <span className="font-medium">{tc("query.failed")}</span>
      <span>{errorMessage(t, error)}</span>
      {onRetry ? (
        <Button size="sm" variant="outline" className="ml-auto" onClick={onRetry}>
          {tc("query.retry")}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * True when nothing is fetching and some query has failed. A disabled query (its key depends on
 * data that never arrived, e.g. the episode id when `/series` fails) is then never going to load.
 */
function useUpstreamFailed(): boolean {
  const client = useQueryClient();
  const cache = client.getQueryCache();
  const subscribe = useCallback((onChange: () => void) => cache.subscribe(onChange), [cache]);
  const snapshot = () =>
    client.isFetching() === 0 &&
    cache.findAll({ predicate: (q) => q.state.status === "error" }).length > 0;
  return useSyncExternalStore(subscribe, snapshot);
}

/** Neutral note for a query that cannot run because what it depends on did not load. */
function QueryBlocked() {
  const { t } = useTranslation("components");
  const client = useQueryClient();
  const retry = () =>
    void client.refetchQueries({ type: "active", predicate: (q) => q.state.status === "error" });
  return (
    <div
      data-testid="query-blocked"
      className="flex flex-wrap items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground"
    >
      <CircleSlash className="size-4" aria-hidden />
      <span>{t("query.blocked")}</span>
      <Button size="sm" variant="outline" className="ml-auto" onClick={retry}>
        {t("query.retry")}
      </Button>
    </div>
  );
}

/**
 * Renders `children(data)` once the query has data; a skeleton while loading; the error
 * otherwise. Pages never fall back to built-in data (M0.5 acceptance: no hard-coded data).
 */
export function QueryState<T>({
  query,
  skeleton,
  children,
}: {
  query: UseQueryResult<T>;
  skeleton?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  const upstreamFailed = useUpstreamFailed();
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.isError) return <QueryError error={query.error} onRetry={() => void query.refetch()} />;
  if (query.fetchStatus === "idle" && upstreamFailed) return <QueryBlocked />;
  return <>{skeleton ?? <Skeleton className="h-40 w-full" />}</>;
}
