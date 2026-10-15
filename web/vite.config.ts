// Modified for AI Drama Studio: Tailwind, "@/" alias, /api proxy to the local backend.
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.DRAMA_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      // SSE needs an unbuffered proxy; Vite's http-proxy streams by default.
      "/api": { target: backend, changeOrigin: false },
    },
  },
});
