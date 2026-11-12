import { defineConfig, devices } from "@playwright/test";

/**
 * Real-environment smoke tests. Writers do NOT run these; the tester runs them
 * after integration against the shared test environment.
 *
 *   GV_E2E_BASE=http://127.0.0.1:8200 GV_E2E_PASSWORD=... npm run e2e:real
 *
 * Never commit the password. `--list` works without any environment.
 */
export default defineConfig({
  testDir: "./e2e/real",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.GV_E2E_BASE || "http://127.0.0.1:8200",
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
