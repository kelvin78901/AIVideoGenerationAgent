import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { SeriesSchema } from "@/api/schemas/series";

export const seriesKeys = {
  detail: (id: string) => ["series", id] as const,
};

export function useSeries(id: string) {
  return useQuery({
    queryKey: seriesKeys.detail(id),
    queryFn: () => api(`/series/${encodeURIComponent(id)}`, SeriesSchema),
  });
}
