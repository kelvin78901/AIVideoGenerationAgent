import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { API_BASE } from "@/api/client";
import { dispatchEvent, EVENT_TYPES, onInjectedEvent } from "@/api/events";
import { callKeys, jobKeys } from "@/api/hooks/useJobs";

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
    const onOpen = () => {
      void client.invalidateQueries({ queryKey: jobKeys.all });
      void client.invalidateQueries({ queryKey: callKeys.all });
    };
    source.addEventListener("open", onOpen);
    for (const type of EVENT_TYPES) {
      source.addEventListener(type, (ev) => {
        let data: unknown;
        try {
          data = JSON.parse((ev as MessageEvent<string>).data);
        } catch {
          console.error(`[events] ${type} payload is not JSON`);
          return;
        }
        dispatchEvent(client, t, type, data);
      });
    }
    const stopInjected = onInjectedEvent((type, data) => dispatchEvent(client, t, type, data));
    return () => {
      stopInjected();
      source.close();
    };
  }, [client, t]);
}
