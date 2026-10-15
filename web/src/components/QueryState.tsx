import type { UseQueryResult } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import type { ReactNode } from "react";
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
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.isError) return <QueryError error={query.error} onRetry={() => void query.refetch()} />;
  return <>{skeleton ?? <Skeleton className="h-40 w-full" />}</>;
}
