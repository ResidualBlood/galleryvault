import { createServer as createTcpServer } from "node:net";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { readerPagePath } from "../src/api/reader";
import { saveFavoriteMonitorSettingsEp } from "../src/api/favorites";
import { expect, test } from "./fixtures/mock";
import { mockFavDlBackend } from "./fixtures/fav-dl/mock";
import { installMaintenanceMock } from "./fixtures/maintenance/mock";
import { mockSettingsBackend } from "./fixtures/settings-sys/mock";

/**
 * Regression coverage for the four product defects found by the C3 gate
 * (test-c3.md): V-04 reader tap zones, V-12 legacy favcat mode save, V-18
 * empty/summary coexistence and G-07 not_configured cookie banner.
 *
 * The harnesses and mocks are the same ones the feature suites use, so these
 * tests exercise the real components and API clients rather than a copy.
 */

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));

let vite: ViteDevServer;
let HARNESS_ROOT = "";

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

function harnessUrl(name: string, params: Record<string, string> = {}): string {
  const query = new URLSearchParams(params);
  return `${HARNESS_ROOT}/${name}/harness.html?${query.toString()}`;
}

function svgPage(page: number, width = 800, height = 1200): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#f4f1ea"/>
  <text x="50%" y="50%" text-anchor="middle" font-family="sans-serif" font-size="${Math.round(width / 10)}" fill="#1c1a17">Page ${page + 1}</text>
</svg>`;
}

async function mockReaderPages(page: Page, total: number): Promise<void> {
  const pageBase = readerPagePath(7, 0).replace(/\/0$/, "");
  await page.route(new RegExp(`${pageBase}/\\d+(?:\\?.*)?$`), async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/pages\/(\d+)/);
    const index = match ? Number.parseInt(match[1], 10) : 0;
    if (index >= total) {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: svgPage(index),
    });
  });
}

test.beforeAll(async () => {
  const port = await freePort();
  vite = await createServer({
    root: PROJECT_ROOT,
    logLevel: "error",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  await vite.listen();
  HARNESS_ROOT = `http://127.0.0.1:${port}/e2e/fixtures`;
});

test.afterAll(async () => {
  await vite?.close();
});

test.describe("C3 gate fixes @c3fix", () => {
  // Harnesses load TypeScript modules from `/src/api/*`; the shared mock fixture
  // matches `**/api/**` and would answer those module requests with JSON.
  test.beforeEach(async ({ page }) => {
    await page.route("**/src/**", (route) => route.continue());
  });

  test("V-04 tap zones receive clicks, toggle bars and turn pages @c3fix", async ({ page }) => {
    await mockReaderPages(page, 12);
    await page.goto(harnessUrl("reader", { total: "12", page: "0", mode: "ltr" }));

    const shell = page.getByTestId("reader-shell");
    await expect(shell).toBeVisible();
    await expect(page.getByTestId("reader-loading")).toHaveCount(0);
    await expect(shell).toHaveAttribute("data-bars", "hidden");

    // The C3 gate failed here: the zone was pointer-events:none, so the click
    // reached the page <img> and Playwright timed out waiting for hit target.
    await page.getByTestId("reader-zone-center").click();
    await expect(shell).toHaveAttribute("data-bars", "visible");
    await expect(page.getByTestId("reader-topbar")).toBeVisible();
    await expect(page.getByTestId("reader-bottombar")).toBeVisible();

    await expect(shell).toHaveAttribute("data-page", "0");
    await page.getByTestId("reader-zone-right").click();
    await expect(shell).toHaveAttribute("data-page", "1");
  });

  test("V-12 legacy favcat mode is normalised and saving returns 2xx @c3fix", async ({ page }) => {
    const state = await mockFavDlBackend(page, { legacyFavoriteMode: true });
    await page.goto(harnessUrl("fav-dl", { view: "favorites" }));

    await expect(page.getByTestId("favorites-view")).toBeVisible();
    const row = page.locator('[data-testid="favcat-row"][data-favcat="0"]');
    await expect(row).toBeVisible();
    // GET returned mode:"gallery"; the old frontend's <select> fell back to the
    // first option, so "incremental" is the expected displayed/edited value.
    await expect(row.getByTestId("favcat-mode").locator("select")).toHaveValue("incremental");

    await row.getByTestId("favcat-enabled").click();
    await expect(page.getByTestId("favorites-save")).toBeEnabled();

    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === saveFavoriteMonitorSettingsEp.path,
    );
    await page.getByTestId("favorites-save").click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const saved = state.writes.find((item) => item.path === saveFavoriteMonitorSettingsEp.path);
    const favorites = (saved?.body as { favorites?: Array<Record<string, unknown>> } | null)
      ?.favorites;
    expect(favorites?.find((item) => item.favcat === 0)).toMatchObject({ mode: "incremental" });
  });

  test("V-18 empty integrity list renders without the scan summary @c3fix", async ({ page }) => {
    await installMaintenanceMock(page, { integrityEmpty: true });
    // The maintenance harness reads the hash path, so the route is `#/integrity`.
    await page.goto(`${HARNESS_ROOT}/maintenance/harness.html?theme=dark#/integrity`);

    await expect(page.getByTestId("integrity-empty")).toBeVisible();
    await expect(page.getByTestId("integrity-summary")).toHaveCount(0);
  });

  test("G-07 not_configured cookie state shows the health banner @c3fix", async ({ page }) => {
    await mockSettingsBackend(page, { cookieState: "not_configured" });
    await page.goto(harnessUrl("settings-sys", { view: "cookie-banner", theme: "dark" }));

    const banner = page.getByTestId("cookie-health-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute("data-cookie-state", "not_configured");
    await expect(banner).toContainText("E-Hentai Cookie");
  });
});

test.describe("C3 round 2 fixes @c3r2", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/src/**", (route) => route.continue());
  });

  test("G-08/V-09 dialogs expose their testid and empty archive input is rejected @c3r2", async ({
    page,
  }) => {
    await mockFavDlBackend(page);
    await page.goto(harnessUrl("fav-dl", { view: "downloads" }));
    await expect(page.getByTestId("downloads-view")).toBeVisible();

    // An empty batch must be rejected with the locale hint, not open a dialog.
    // DownloadsView passes these ids as the Dialog `testid` prop; the root is a
    // Teleport target, so a plain `data-testid` attribute never reaches the DOM.
    await page.getByTestId("downloads-add-archive").click();
    await expect(page.getByRole("status").filter({ hasText: "没有识别到画廊链接" })).toBeVisible();
    await expect(page.getByTestId("downloads-archive-dialog")).toHaveCount(0);

    await page.getByTestId("downloads-urls").fill("123456/abcdef");
    await page.getByTestId("downloads-add-archive").click();
    const archive = page.getByTestId("downloads-archive-dialog");
    await expect(archive).toBeVisible();
    await expect(archive).toHaveAttribute("role", "dialog");
    await page.keyboard.press("Escape");
    await expect(archive).toHaveCount(0);

    await page.getByTestId("downloads-retry-all").click();
    await expect(page.getByTestId("downloads-retry-all-dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("downloads-retry-all-dialog")).toHaveCount(0);
  });

  test("V-04 Escape close does not swallow an immediate ArrowRight page turn @c3r2", async ({
    page,
  }) => {
    await mockReaderPages(page, 12);
    await page.goto(harnessUrl("reader", { total: "12", page: "0", mode: "ltr" }));

    const shell = page.getByTestId("reader-shell");
    await expect(shell).toBeVisible();
    await expect(page.getByTestId("reader-loading")).toHaveCount(0);
    await page.getByTestId("reader-zone-center").click();
    await page.getByTestId("reader-settings").click();
    await expect(page.getByTestId("reader-settings-panel")).toBeVisible();
    await expect(shell).toHaveAttribute("data-page", "0");

    // Dispatch both keydowns in the same task so the 80 ms window is exercised
    // deterministically: Escape must not refresh the page-turn timestamp.
    await page.evaluate(() => {
      for (const key of ["Escape", "ArrowRight"]) {
        window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      }
    });

    await expect(page.getByTestId("reader-settings-panel")).toHaveCount(0);
    await expect(shell).toHaveAttribute("data-page", "1");
  });
});
