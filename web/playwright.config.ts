/**
 * Playwright: `pnpm e2e` (smoke tests, run in CI) and `pnpm shots` (screenshots for
 * docs/studio/reports/ui/). Starts its own mock backend (temporary DRAMA_HOME) and Vite server on
 * separate ports, so a running `start.ps1` / `start.sh` session is never touched.
 */
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig, devices } from "@playwright/test";

const BACKEND_PORT = 8765;
const WEB_PORT = 5183;
const BASE_URL = `http://127.0.0.1:${WEB_PORT}`;

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
    { name: "smoke", testMatch: /smoke\.spec\.ts/, use: { ...desktop } },
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
        DRAMA_WEB_ORIGINS: BASE_URL,
      },
    },
    {
      command: `pnpm exec vite --port ${WEB_PORT} --strictPort`,
      url: BASE_URL,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { DRAMA_BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
});
