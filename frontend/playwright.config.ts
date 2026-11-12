import { defineConfig, devices } from "@playwright/test";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));

/**
 * Parallel worktrees must not fight over one preview port: derive a stable
 * port in 4200–4999 from the worktree path, overridable with GV_E2E_PORT.
 */
function worktreePort(): string {
  if (process.env.GV_E2E_PORT) return process.env.GV_E2E_PORT;
  const digest = createHash("sha1").update(projectRoot).digest();
  return String(4200 + (digest.readUInt16BE(0) % 800));
}

const port = worktreePort();
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["real/**"],
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL,
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
  webServer: {
    command: `npm run build && npm run preview -- --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
    cwd: projectRoot,
  },
});
