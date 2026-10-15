/**
 * Screenshots of the clickable prototype (docs/studio/prototype/*.dc.html) for the side-by-side
 * comparison in docs/studio/reports/ui/. The `.dc.html` files need the design-canvas runtime,
 * which is not in the repo: pass the `dc-runtime.js` downloaded from Kelvin's prototype artifact.
 * It is copied next to the pages as `support.js` in a temporary folder and never committed.
 *
 *   pnpm exec tsx scripts/prototype-shots.ts --runtime <dc-runtime.js> [--only Main,Spec]
 */
import { copyFileSync, mkdirSync, mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { chromium } from "@playwright/test";

const root = fileURLToPath(new URL("../..", import.meta.url));
const protoDir = join(root, "docs/studio/prototype");
const outDir = join(root, "docs/studio/reports/ui/prototype");

const { values } = parseArgs({
  options: { runtime: { type: "string" }, only: { type: "string" } },
});
if (!values.runtime) throw new Error("--runtime <path to dc-runtime.js> is required");

interface Board {
  w: number;
  h: number;
  title: string;
}
const canvas = JSON.parse(readFileSync(join(protoDir, "canvas.json"), "utf8")) as {
  boards: Record<string, Board>;
};
const only = values.only?.split(",").map((s) => s.trim());

const site = mkdtempSync(join(tmpdir(), "dc-proto-"));
for (const f of readdirSync(protoDir)) copyFileSync(join(protoDir, f), join(site, f));
copyFileSync(resolve(values.runtime), join(site, "support.js"));

const types: Record<string, string> = { ".html": "text/html", ".js": "text/javascript" };
const server = createServer((req, res) => {
  // Flat folder: drop any slashes so a request can never leave it.
  const name = basename(decodeURIComponent(new URL(req.url ?? "/", "http://x").pathname));
  try {
    const body = readFileSync(join(site, name));
    res.writeHead(200, { "content-type": types[extname(name)] ?? "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
const port = (server.address() as AddressInfo).port;

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
try {
  for (const [file, board] of Object.entries(canvas.boards)) {
    const name = file.replace(/\.dc\.html$/, "");
    if (only && !only.includes(name)) continue;
    const page = await browser.newPage({ viewport: { width: board.w, height: 900 } });
    await page.goto(`http://127.0.0.1:${port}/${file}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(800); // fonts and the runtime's first render
    const path = join(outDir, `${name}.jpg`);
    await page.screenshot({ path, fullPage: true, type: "jpeg", quality: 80 });
    console.log(`${name}: ${path}`);
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}
