// Modified for AI Drama Studio: new entry point; the upstream Hermes UI lives in src/legacy/.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@/i18n";
import "@/styles/globals.css";
import { App } from "@/app/App";

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing from index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
