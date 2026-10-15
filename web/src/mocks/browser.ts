import { setupWorker } from "msw/browser";

import { handlers } from "@/mocks/handlers";

/** Starts the demo-data service worker; unhandled requests go to the real backend. */
export async function startDemoWorker(): Promise<void> {
  await setupWorker(...handlers).start({
    onUnhandledRequest: "bypass",
    quiet: true,
    serviceWorker: { url: "/mockServiceWorker.js" },
  });
}
