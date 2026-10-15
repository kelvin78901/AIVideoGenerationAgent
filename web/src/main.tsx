// Modified for AI Drama Studio: new entry point; the upstream Hermes UI lives in src/legacy/.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@/i18n";
import "@/styles/globals.css";
import { App } from "@/app/App";
import { DEMO_DATA } from "@/app/demo";

async function main(): Promise<void> {
  // Start the demo worker before the first request so every page sees the same data.
  if (DEMO_DATA) await (await import("@/mocks/browser")).startDemoWorker();
  const root = document.getElementById("root");
  if (!root) throw new Error("#root element missing from index.html");
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void main();
