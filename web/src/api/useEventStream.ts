import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { API_BASE } from "@/api/client";
import { callKeys, jobKeys, upsertJob } from "@/api/hooks/useJobs";
import type { Job } from "@/api/types";

interface ToastEvent {
  level?: "success" | "info" | "warning" | "error";
  code: string;
  params?: Record<string, unknown>;
}

/**
 * One EventSource for the whole app. The browser reconnects by itself and resends
 * Last-Event-ID, so the backend replays what was missed; after (re)connecting we also
 * refetch, which covers events from before the first connection.
 */
export function useEventStream(): void {
  const client = useQueryClient();
  const { t } = useTranslation();

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/events`);
    const parse = <T>(ev: Event): T => JSON.parse((ev as MessageEvent<string>).data) as T;

    const onOpen = () => {
      void client.invalidateQueries({ queryKey: jobKeys.all });
      void client.invalidateQueries({ queryKey: callKeys.all });
    };
    const onJob = (ev: Event) => upsertJob(client, parse<Job>(ev));
    const onCost = () => void client.invalidateQueries({ queryKey: callKeys.all });
    const onToast = (ev: Event) => {
      const data = parse<ToastEvent>(ev);
      const text = t(`toast.${data.code}` as "toast.generic", {
        ...data.params,
        code: data.code,
        defaultValue: t("toast.generic", { code: data.code }),
      });
      toast[data.level ?? "info"](text);
    };

    source.addEventListener("open", onOpen);
    source.addEventListener("job.updated", onJob);
    source.addEventListener("cost.updated", onCost);
    source.addEventListener("toast", onToast);
    return () => source.close();
  }, [client, t]);
}
