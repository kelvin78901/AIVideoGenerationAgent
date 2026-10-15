import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

import { TooltipProvider } from "@/components/ui/tooltip";

import "@/i18n";

/** A fresh query cache per test; no retries so failures surface immediately. */
export function makeTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
}

export function renderAt(ui: ReactElement, path = "/", client = makeTestQueryClient()) {
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <TooltipProvider>{ui}</TooltipProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}
