/**
 * Playwright: `pnpm e2e` (smoke tests and the no-demo-data round with the flows they depend on,
 * `seeded` → `m4` → `real` → `smoke`; run in CI) and `pnpm shots`
 * (screenshots for docs/studio/reports/ui/). Starts its own mock backend (temporary DRAMA_HOME)
 * and two Vite servers on separate ports — one with the MSW demo data, one without
 * (`VITE_DEMO_DATA=0`) — so a running `start.ps1` / `start.sh` session is never touched.
 */
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig, devices } from "@playwright/test";

const BACKEND_PORT = 8765;
const WEB_PORT = 5183;
const BASE_URL = `http://127.0.0.1:${WEB_PORT}`;
const REAL_PORT = 5184; // VITE_DEMO_DATA=0: the backend only
const REAL_URL = `http://127.0.0.1:${REAL_PORT}`;

// Playwright loads this config in every worker; the env var keeps one data folder per run.
const home = process.env.DRAMA_E2E_HOME ?? mkdtempSync(join(tmpdir(), "drama-e2e-"));
process.env.DRAMA_E2E_HOME = home;
const envFile = join(home, "empty.env"); // never read the developer's real .env
writeFileSync(envFile, "");

// The prototype artboards are 1440 px wide; the device preset alone would give 1280 × 720.
// Demo timestamps are Beijing time (+08:00); pin the zone so screenshots match the prototype.
const desktop = {
  ...devices["Desktop Chrome"],
  viewport: { width: 1440, height: 900 },
  timezoneId: "Asia/Shanghai",
};

export default defineConfig({
  testDir: "e2e",
  outputDir: "node_modules/.playwright/results",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: BASE_URL, locale: "zh-CN" },
  projects: [
    // The demo as seeded, before the M2 flows below change it.
    { name: "seeded", testMatch: /seeded\.spec\.ts/, use: { ...desktop, baseURL: REAL_URL } },
    // The demo storyboard confirmed (M4), on the dubbed lines `seeded` made.
    {
      name: "m4",
      testMatch: /m4\.spec\.ts/,
      dependencies: ["seeded"],
      use: { ...desktop, baseURL: REAL_URL },
    },
    {
      name: "real",
      testMatch: /real\.spec\.ts/,
      dependencies: ["m4"],
      use: { ...desktop, baseURL: REAL_URL },
    },
    // Last: the M2 flows re-script the demo's episode 1 (its assets' scenes go with it).
    {
      name: "smoke",
      testMatch: /(smoke|m2)\.spec\.ts/,
      dependencies: ["seeded", "m4", "real"],
      use: { ...desktop },
    },
    { name: "shots", testMatch: /shots\.spec\.ts/, use: { ...desktop } },
  ],
  webServer: [
    {
      // `python -m`, not the `drama-studio` entry exe: Windows Application Control may block it.
      command: `uv run python -m drama_series_agent.studio_cli dev --port ${BACKEND_PORT}`,
      cwd: "..",
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        DRAMA_HOME: home,
        DRAMA_MOCK: "1",
        DRAMA_ENV_FILE: envFile,
        DRAMA_WEB_ORIGINS: `${BASE_URL},${REAL_URL}`,
      },
    },
    {
      command: `pnpm exec vite --port ${WEB_PORT} --strictPort`,
      url: BASE_URL,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { DRAMA_BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}` },
    },
    {
      command: `pnpm exec vite --port ${REAL_PORT} --strictPort`,
      url: REAL_URL,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { DRAMA_BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}`, VITE_DEMO_DATA: "0" },
    },
  ],
});
