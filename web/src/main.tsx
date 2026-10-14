// Modified for AI Drama Studio: entry point; the upstream Hermes UI now lives in src/legacy/.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import LegacyApp from "@/legacy/App";
import "@/legacy/index.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing from index.html");

createRoot(root).render(
  <StrictMode>
    <LegacyApp />
  </StrictMode>,
);
