import { defineConfig, devices } from "@playwright/test";
import { REAL_STORAGE_STATE } from "./e2e/real/storage";

/**
 * Real-environment smoke tests. Writers do NOT run these; the tester runs them
 * after integration against the shared test environment.
 *
 *   GV_E2E_BASE=http://127.0.0.1:8200 GV_E2E_PASSWORD=... npm run e2e:real
 *
 * Never commit the password. `--list` works without any environment.
 *
 * `globalSetup` logs in once and stores the session + CSRF cookie; every browser
 * context reuses it. nginx limits POST /login to 10r/m (burst 5), so per-test
 * logins made the 36-case parity run report 503s from the 17th case onwards.
 */
export default defineConfig({
  testDir: "./e2e/real",
  globalSetup: "./e2e/real/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.GV_E2E_BASE || "http://127.0.0.1:8200",
    storageState: REAL_STORAGE_STATE,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1280, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
