import { mkdirSync } from "node:fs";
import { createServer as createTcpServer } from "node:net";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { expect, test } from "./fixtures/mock";
import {
  READER_GID,
  READER_TOKEN,
} from "./fixtures/online-reader/data";
import {
  mockOnlineReaderBackend,
  type ReaderMockOptions,
} from "./fixtures/online-reader/mock";

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

let vite: ViteDevServer;
let HARNESS = "";

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createTcpServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      const port = typeof address === "object" && address ? address.port : 0;
      probe.close(() => resolve(port));
    });
  });
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  const port = await freePort();
  vite = await createServer({
    root: PROJECT_ROOT,
    logLevel: "error",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  await vite.listen();
  HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/online-reader/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

interface HarnessOptions {
  theme?: "dark" | "light";
  lang?: "zh" | "en";
  view?: "reader" | "continue";
  page?: number;
  imageMode?: "direct" | "proxy";
}

function harnessUrl(options: HarnessOptions = {}): string {
  const params = new URLSearchParams();
  params.set("gid", String(READER_GID));
  params.set("token", READER_TOKEN);
  if (options.theme) params.set("theme", options.theme);
  if (options.lang) params.set("lang", options.lang);
  if (options.view) params.set("view", options.view);
  if (typeof options.page === "number") params.set("page", String(options.page));
  if (options.imageMode) params.set("imageMode", options.imageMode);
  return `${HARNESS}?${params.toString()}`;
}

async function allowViteModules(page: Page): Promise<void> {
  /*
   * The shared mock fixture routes `**\/api/**` to JSON. The Vite dev server
   * serves TypeScript modules from `/src/api/...`, which would also match that
   * glob, so let all `/src/**` requests reach Vite untouched.
   */
  await page.route("**/src/**", (route) => route.continue());
}

async function openReader(
  page: Page,
  mock: ReaderMockOptions = {},
  options: HarnessOptions = {},
) {
  const metrics = await mockOnlineReaderBackend(page, mock);
  await allowViteModules(page);
  await page.goto(harnessUrl(options));
  const shell = page.getByTestId("reader-shell");
  await expect(page.getByTestId("online-reader")).toBeVisible();
  await expect(shell).toBeVisible();
  await expect(shell).toHaveAttribute("data-total", "10");
  return { shell, metrics };
}

function watchConsole(page: Page): string[] {
  const issues: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (
      message.type() === "error" &&
      /content security policy|refused to (?:load|execute|connect)/i.test(text)
    ) {
      issues.push(text);
    }
  });
  page.on("pageerror", (error) => {
    if (/content security policy/i.test(error.message)) issues.push(error.message);
  });
  return issues;
}

async function turn(page: Page, times: number, key: "ArrowRight" | "ArrowLeft" = "ArrowRight") {
  for (let index = 0; index < times; index += 1) {
    await page.keyboard.press(key);
    await page.waitForTimeout(140);
  }
}

test("direct mode reads ten pages with zero server image requests @online-reader", async ({
  page,
}) => {
  const csp = watchConsole(page);
  const { shell, metrics } = await openReader(page);

  await turn(page, 9);
  await expect(shell).toHaveAttribute("data-page", "9");

  expect(metrics.proxyImages).toEqual([]);
  expect(metrics.resolves.length).toBeGreaterThanOrEqual(10);
  expect(metrics.maxInflightResolves).toBeLessThanOrEqual(2);
  expect(metrics.blockedExternal).toEqual([]);

  expect(metrics.images.length).toBeGreaterThan(0);
  for (const image of metrics.images) {
    expect(image.url).toContain(".hath.network:8443");
    expect(image.referer).toBeNull();
    expect(image.cookie).toBeNull();
  }

  expect(await page.locator("iframe").count()).toBe(0);
  expect(csp).toEqual([]);
});

test("a dead first image is re-resolved with retry=1 @online-reader", async ({ page }) => {
  const csp = watchConsole(page);
  const { metrics } = await openReader(page, { scenario: "retry" });

  await expect
    .poll(() => metrics.resolves.some((item) => item.page === 2 && item.retry === 1))
    .toBe(true);
  expect(metrics.resolves.some((item) => item.page === 2 && item.retry === 0)).toBe(true);
  await expect
    .poll(() => metrics.images.some((image) => /\/2-0-dead\.jpg/.test(image.url)))
    .toBe(true);
  await expect
    .poll(() => metrics.images.some((image) => /\/2-1-ok\.jpg/.test(image.url)))
    .toBe(true);

  await expect(page.locator('[data-testid="reader-page"] img').first()).toBeVisible();
  await expect(page.getByTestId("online-reader-blocked")).toHaveCount(0);
  expect(csp).toEqual([]);
});

test("exhausted retries offer the proxy and the official page @online-reader", async ({
  page,
}) => {
  const csp = watchConsole(page);
  const { metrics } = await openReader(page, { scenario: "blocked" });

  const panel = page.getByTestId("online-reader-blocked");
  await expect(panel).toBeVisible();
  await expect(panel).toHaveAttribute("data-page", "2");
  await expect(panel).toHaveAttribute("data-reason", "image_failed");

  const official = page.getByTestId("online-reader-official");
  await expect(official).toHaveAttribute(
    "href",
    `https://exhentai.org/g/${READER_GID}/${READER_TOKEN}/`,
  );
  await expect(official).toHaveAttribute("target", "_blank");
  await expect(official).toHaveAttribute("rel", "noopener noreferrer");

  // Blocked page tried retry 0, 1 and 2 before giving up.
  const attempts = metrics.resolves.filter((item) => item.page === 3).map((item) => item.retry);
  expect(attempts).toEqual([0, 1, 2]);

  await page.waitForTimeout(300);
  const beforeSwitch = metrics.resolves.length;

  await page.getByTestId("online-reader-use-proxy").click();
  await expect(page.getByTestId("online-reader")).toHaveAttribute("data-mode", "proxy");
  await expect.poll(() => metrics.proxyImages.length).toBeGreaterThan(0);
  expect(
    await page.evaluate(() => localStorage.getItem("gv_online_image_mode")),
  ).toBe("proxy");

  await page.keyboard.press("ArrowRight");
  await expect
    .poll(() => metrics.proxyImages.some((url) => /\/pages\/2\/image$/.test(url)))
    .toBe(true);
  expect(metrics.resolves.length).toBe(beforeSwitch);
  expect(await page.locator("iframe").count()).toBe(0);
  expect(csp).toEqual([]);
});

test("an expired page is resolved again when turned back to @online-reader", async ({
  page,
}) => {
  const csp = watchConsole(page);
  const { metrics } = await openReader(page, { scenario: "expiry" });

  await expect
    .poll(() => metrics.resolves.filter((item) => item.page === 1).length)
    .toBeGreaterThanOrEqual(1);

  await page.waitForTimeout(2_200);
  await turn(page, 1);
  await turn(page, 1, "ArrowLeft");

  await expect
    .poll(() => metrics.resolves.filter((item) => item.page === 1).length)
    .toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId("reader-shell")).toHaveAttribute("data-page", "0");
  expect(csp).toEqual([]);
});

test("429 image_limit stops resolution and shows the quota @online-reader", async ({
  page,
}) => {
  const csp = watchConsole(page);
  const { metrics } = await openReader(page, { scenario: "quota" });

  await turn(page, 6);

  const notice = page.getByTestId("online-reader-quota");
  await expect(notice).toBeVisible();
  await expect(page.getByTestId("online-reader-quota-usage")).toContainText("5000");
  expect(metrics.quotaRequests).toBeGreaterThan(0);

  const before = metrics.resolves.length;
  await page.waitForTimeout(600);
  expect(metrics.resolves.length).toBe(before);
  expect(metrics.resolvesAfterQuota).toBe(0);
  expect(csp).toEqual([]);
});

test("reloading the reader resumes the stored page @online-reader", async ({ page }) => {
  const csp = watchConsole(page);
  const { shell, metrics } = await openReader(page);

  await turn(page, 3);
  await expect(shell).toHaveAttribute("data-page", "3");
  await expect.poll(() => metrics.progressSaves.at(-1)?.page).toBe(4);
  await page.waitForTimeout(700);

  await page.reload();
  await expect(page.getByTestId("online-reader")).toBeVisible();
  const reloaded = page.getByTestId("reader-shell");
  await expect(reloaded).toBeVisible();
  await expect(reloaded).toHaveAttribute("data-page", "3");
  await expect(reloaded).toHaveAttribute("data-total", "10");
  expect(csp).toEqual([]);
});

test("continue-reading section links back to the stored page @online-reader", async ({
  page,
}) => {
  const csp = watchConsole(page);
  await mockOnlineReaderBackend(page, { historyCount: 3 });
  await allowViteModules(page);
  await page.goto(harnessUrl({ view: "continue" }));

  const section = page.getByTestId("online-continue");
  await expect(section).toBeVisible();
  await expect(section).toHaveAttribute("data-count", "3");
  const items = page.getByTestId("online-continue-item");
  await expect(items).toHaveCount(3);
  await expect(items.first()).toHaveAttribute(
    "href",
    /#\/online\/g\/910000\/tok910000\/read\/2$/,
  );
  await expect(page.getByTestId("online-continue-progress").first()).toContainText("3");
  expect(csp).toEqual([]);
});

test("screenshots cover dark/light x desktop/mobile @online-reader", async ({ page }) => {
  const csp = watchConsole(page);
  await mockOnlineReaderBackend(page);
  await allowViteModules(page);
  const themes = ["dark", "light"] as const;
  const viewports = [
    { width: 1280, height: 900, label: "1280" },
    { width: 390, height: 844, label: "390" },
  ];

  for (const theme of themes) {
    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(harnessUrl({ theme }));
      await expect(page.getByTestId("reader-shell")).toBeVisible();
      await expect(page.getByTestId("online-reader-actions")).toBeVisible();
      await expect(page.locator('[data-testid="reader-page"] img').first()).toBeVisible();
      await page.waitForTimeout(250);
      await page.screenshot({
        path: join(SHOTS, `online-reader-${theme}-${viewport.label}.png`),
        fullPage: false,
      });
    }
  }
  expect(csp).toEqual([]);
});
