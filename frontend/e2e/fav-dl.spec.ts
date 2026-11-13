import { mkdirSync } from "node:fs";
import { createServer as createTcpServer } from "node:net";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import {
  cancelDownloadEp,
  clearSuccessfulDownloadsEp,
  createDownloadBatchEp,
  deleteDownloadEp,
  retryAllDownloadsEp,
  retryDownloadEp,
} from "@/api/downloads";
import {
  checkAllFavoritesEp,
  downloadMissingFavoritesEp,
  downloadSelectedFavoritesEp,
  moveFavoritesEp,
  removeFavoritesEp,
  saveFavoriteMonitorSettingsEp,
  syncFavoriteCategoriesEp,
} from "@/api/favorites";
import {
  clearAllProgressEp,
  clearGalleryProgressEp,
  clearHistoryEp,
} from "@/api/history";
import { sessionEp } from "@/api/auth";
import { notificationsEp } from "@/api/system";
import { mockFavDlBackend, type FavDlMockState } from "./fixtures/fav-dl/mock";

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

type Theme = "dark" | "light";
type HarnessView = "favorites" | "favlist" | "downloads" | "history";

function harnessUrl(options: {
  view: HarnessView;
  theme?: Theme;
  path?: string;
}): string {
  const params = new URLSearchParams();
  params.set("view", options.view);
  params.set("theme", options.theme ?? "dark");
  if (options.path) params.set("path", options.path);
  return `${HARNESS}?${params.toString()}`;
}

/**
 * Minimal shell backend for the real-route test. The shared e2e fixture glob
 * also matches the Vite dev-server path `/src/api/*.ts` and breaks the harness,
 * so this matcher only accepts real API paths (second path segment = "api").
 */
async function installShellMock(page: Page): Promise<void> {
  // Registered first so it is the lowest-priority API route; the fav-dl mock
  // (registered later) can `fallback()` into it for unrelated endpoints.
  await page.route(
    (url) => url.pathname.split("/")[1] === "api",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
    },
  );
  await page.route(
    (url) => url.pathname === notificationsEp.path,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], unread: 0 }),
      });
    },
  );
  await page.route(
    (url) => url.pathname === sessionEp.path,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          authenticated: true,
          auth_required: true,
          must_change_password: false,
          cookie_health: { state: "ok" },
        }),
      });
    },
  );
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true });
}

function writeCount(state: FavDlMockState, path: string, method?: string): number {
  return state.writes.filter(
    (item) => item.path === path && (!method || item.method === method),
  ).length;
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
  HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/fav-dl/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

test.beforeEach(async ({ page, baseURL }) => {
  await page.context().addCookies([
    { name: "galleryvault_csrf", value: "test-csrf", url: HARNESS },
    ...(baseURL
      ? [{ name: "galleryvault_csrf", value: "test-csrf", url: baseURL }]
      : []),
  ]);
});

test.describe("favourites / downloads / history @fav-dl", () => {
  test("favourites overview saves each folder's monitor config @fav-dl", async ({ page }) => {
    const csp = watchConsole(page);
    const state = await mockFavDlBackend(page);

    await page.goto(harnessUrl({ view: "favorites" }));
    await expect(page.getByTestId("favorites-view")).toBeVisible();
    await expect(page.getByTestId("favorites-table")).toBeVisible();
    await expect(page.getByTestId("favcat-row")).toHaveCount(3);
    await expect(page.getByTestId("favcat-ring").first()).toBeVisible();

    const row = page.locator('[data-testid="favcat-row"][data-favcat="1"]');
    await row.getByTestId("favcat-enabled").click();
    await row.getByTestId("favcat-mode").locator("select").selectOption("force");
    await row.getByTestId("favcat-interval").fill("90");
    await expect(page.getByTestId("favorites-save")).toBeEnabled();
    await page.getByTestId("favorites-save").click();

    await expect.poll(() => writeCount(state, saveFavoriteMonitorSettingsEp.path)).toBe(1);
    const settings = state.writes.find((item) => item.path === saveFavoriteMonitorSettingsEp.path);
    const favorites = (settings?.body as { favorites?: Array<Record<string, unknown>> })
      .favorites;
    expect(settings?.csrf).toBe("test-csrf");
    expect(Array.isArray(favorites)).toBe(true);
    expect(favorites?.find((item) => item.favcat === 1)).toMatchObject({
      enabled: false,
      mode: "force",
      poll_interval_minutes: 90,
    });

    await page.getByTestId("favorites-check-all").click();
    await expect(page.getByTestId("favorites-sync")).toBeEnabled();
    await page.getByTestId("favorites-sync").click();
    await page.getByTestId("favorites-download-missing").click();
    await expect.poll(() => writeCount(state, checkAllFavoritesEp.path)).toBe(1);
    await expect.poll(() => writeCount(state, syncFavoriteCategoriesEp.path)).toBe(1);
    await expect.poll(() => writeCount(state, downloadMissingFavoritesEp.path)).toBe(1);

    expect(csp).toEqual([]);
  });

  test("favlist sends all 15 filters through one constructor, then downloads / moves / removes",
    async ({ page }) => {
      const csp = watchConsole(page);
      const state = await mockFavDlBackend(page);

      await page.goto(
        harnessUrl({ view: "favlist", path: "/favorites/1?page_size=12" }),
      );
      await expect(page.getByTestId("favlist-view")).toBeVisible();
      await expect(page.getByTestId("favlist-grid")).toBeVisible();
      await expect(page.locator(".fav-card").first()).toBeVisible();
      expect(await page.locator(".fav-card").count()).toBeGreaterThanOrEqual(12);

      await page.getByTestId("favlist-advanced-toggle").click();
      await page.getByTestId("favlist-q").locator("input").fill("dragon");
      await page.getByTestId("favlist-category").locator("select").selectOption("manga");
      await page.getByTestId("favlist-language").locator("select").selectOption("chinese");
      await page.getByTestId("favlist-order").locator("select").selectOption("posted_at_desc");
      await page
        .getByTestId("favlist-read-status")
        .locator("select")
        .selectOption("unread");
      await page
        .getByTestId("favlist-min-rating")
        .locator("select")
        .selectOption("4.5");
      await page.getByTestId("favlist-page-min").locator("input").fill("10");
      await page.getByTestId("favlist-page-max").locator("input").fill("90");
      await page.getByTestId("favlist-size-min").locator("input").fill("1.5");
      await page.getByTestId("favlist-size-max").locator("input").fill("20");
      await page.getByTestId("favlist-posted-from").locator("input").fill("2025-01-01");
      await page.getByTestId("favlist-posted-to").locator("input").fill("2025-12-31");
      await page.getByTestId("favlist-uploader").locator("input").fill("artist");
      await page
        .getByTestId("favlist-image-quality")
        .locator("select")
        .selectOption("original");
      await page
        .getByTestId("favlist-local-rating")
        .locator("select")
        .selectOption("3");
      await page.locator('form[role="search"] button[type="submit"]').click();

      await expect
        .poll(() => state.favoriteItemRequests.at(-1)?.get("order_by"))
        .toBe("posted_at_desc");
      const params = state.favoriteItemRequests.at(-1);
      expect(params).toBeTruthy();
      expect(params?.get("q")).toBe("dragon");
      expect(params?.get("category")).toBe("manga");
      expect(params?.get("order_by")).toBe("posted_at_desc");
      expect(params?.get("read_status")).toBe("unread");
      expect(params?.get("page_min")).toBe("10");
      expect(params?.get("page_max")).toBe("90");
      expect(params?.get("min_rating")).toBe("4.5");
      expect(params?.get("size_min")).toBe("1572864");
      expect(params?.get("size_max")).toBe("20971520");
      expect(params?.get("posted_from")).toBe("2025-01-01");
      expect(params?.get("posted_to")).toBe("2025-12-31");
      expect(params?.get("uploader")).toBe("artist");
      expect(params?.get("image_quality")).toBe("original");
      expect(params?.get("min_local_rating")).toBe("3");
      expect(params?.get("tags")).toContain("language:chinese");
      expect(params?.get("page")).toBe("1");

      const first = page.locator(".fav-card").first();
      await first.locator('input[type="checkbox"]').check();
      await expect(page.getByTestId("favlist-download")).toContainText("(1)");
      await page.getByTestId("favlist-download").click();
      await expect.poll(() => writeCount(state, downloadSelectedFavoritesEp.path)).toBe(1);
      const queued = state.writes.find(
        (item) => item.path === downloadSelectedFavoritesEp.path,
      );
      expect((queued?.body as { gids?: number[] }).gids).toHaveLength(1);

      await first.locator('input[type="checkbox"]').check();
      await page.getByTestId("favlist-move").click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.getByTestId("favlist-move-target").locator("select").selectOption("2");
      await page.getByTestId("favlist-move-confirm").click();
      await expect.poll(() => writeCount(state, moveFavoritesEp.path)).toBe(1);
      const moved = state.writes.find((item) => item.path === moveFavoritesEp.path);
      expect(moved?.body).toMatchObject({ target_favcat: 2 });

      await first.locator('input[type="checkbox"]').check();
      await page.getByTestId("favlist-remove").click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.getByTestId("favlist-remove-confirm").click();
      await expect.poll(() => writeCount(state, removeFavoritesEp.path)).toBe(1);
      const removed = state.writes.find((item) => item.path === removeFavoritesEp.path);
      expect((removed?.body as { gids?: number[] }).gids).toHaveLength(1);

      expect(csp).toEqual([]);
    });

  test("downloads page pauses polling while hidden, then handles batch / retry / delete / pause",
    async ({ page }) => {
      const csp = watchConsole(page);
      const state = await mockFavDlBackend(page);

      await page.goto(harnessUrl({ view: "downloads" }));
      await expect(page.getByTestId("downloads-view")).toBeVisible();
      await expect(page.locator(".download-item")).toHaveCount(6);
      await expect(page.getByTestId("downloads-gp")).toContainText("12345 GP");
      await expect(page.getByTestId("downloads-quota")).toContainText("86/100");
      await expect(page.getByTestId("downloads-task-meta").first()).toContainText("12/40");
      await expect(page.getByTestId("downloads-task-meta").first()).toContainText("1.5 MB/s");
      await expect(page.getByTestId("downloads-task-meta").first()).toContainText("1m 35s");

      await page.waitForTimeout(2300);
      const beforeHidden = state.downloadRequests.length;
      expect(beforeHidden).toBeGreaterThan(0);
      await page.evaluate(() => {
        Object.defineProperty(document, "visibilityState", {
          configurable: true,
          get: () => "hidden",
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      await page.waitForTimeout(2600);
      expect(state.downloadRequests.length).toBe(beforeHidden);

      await page.evaluate(() => {
        Object.defineProperty(document, "visibilityState", {
          configurable: true,
          get: () => "visible",
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      await expect
        .poll(() => state.downloadRequests.length, { timeout: 5000 })
        .toBeGreaterThan(beforeHidden);

      await page
        .getByTestId("downloads-status-segmented")
        .locator('[data-segmented-value="failed"]')
        .click();
      await expect(page.locator(".download-item")).toHaveCount(1);
      await expect(page.locator(".download-item").first()).toHaveAttribute(
        "data-status",
        "failed",
      );
      await expect
        .poll(() => state.downloadRequests.at(-1)?.get("status"))
        .toBe("failed");
      await page
        .getByTestId("downloads-status-segmented")
        .locator('[data-segmented-value="all"]')
        .click();
      await expect(page.locator(".download-item")).toHaveCount(6);

      await page.getByTestId("downloads-urls").locator("textarea").fill(
        "https://e-hentai.org/g/123456/abcdef/\n987/abc123",
      );
      await page.getByTestId("downloads-quality").locator("select").selectOption("original");
      await page.getByTestId("downloads-add").click();
      await expect.poll(() => writeCount(state, createDownloadBatchEp.path)).toBe(1);
      const batch = state.writes.find((item) => item.path === createDownloadBatchEp.path);
      expect(batch?.body).toMatchObject({ quality: "original" });
      expect((batch?.body as { items?: unknown[] }).items).toHaveLength(2);

      await page.getByTestId("downloads-pause").click();
      await expect(page.getByTestId("downloads-paused-badge")).toBeVisible();
      await expect.poll(() => state.paused).toBe(true);

      await page
        .locator('.download-item[data-task-id="1"]')
        .getByTestId("downloads-cancel")
        .click();
      await expect
        .poll(() => writeCount(state, cancelDownloadEp.path.replace("{id}", "1")))
        .toBe(1);
      await page
        .locator('.download-item[data-task-id="4"]')
        .getByTestId("downloads-retry")
        .click();
      await expect
        .poll(() => writeCount(state, retryDownloadEp.path.replace("{id}", "4")))
        .toBe(1);

      await page
        .locator('.download-item[data-task-id="6"]')
        .getByTestId("downloads-delete")
        .click();
      await page.getByTestId("downloads-delete-confirm").click();
      await expect
        .poll(() => writeCount(state, deleteDownloadEp.path.replace("{id}", "6"), "DELETE"))
        .toBe(1);

      await page.getByTestId("downloads-more-trigger").click();
      await page.getByTestId("downloads-clear-success").click();
      await page.getByTestId("downloads-clear-confirm").click();
      await expect.poll(() => writeCount(state, clearSuccessfulDownloadsEp.path)).toBe(1);

      await page.getByTestId("downloads-more-trigger").click();
      await page.getByTestId("downloads-retry-all").click();
      await page.getByTestId("downloads-retry-all-confirm").click();
      await expect.poll(() => writeCount(state, retryAllDownloadsEp.path)).toBe(1);

      await page.getByTestId("downloads-select-all").click();
      await page.getByTestId("downloads-delete-selected").click();
      await expect(page.getByText(/删除所选的 6 个下载任务/)).toBeVisible();
      await page.getByTestId("downloads-delete-confirm").click();
      await expect
        .poll(() => state.writes.filter((item) => item.method === "DELETE").length)
        .toBeGreaterThanOrEqual(7);
      expect(csp).toEqual([]);
    });

  test("history clears all history, all progress and one gallery's progress @fav-dl", async ({
    page,
  }) => {
    const csp = watchConsole(page);
    const state = await mockFavDlBackend(page);

    await page.goto(harnessUrl({ view: "history" }));
    await expect(page.getByTestId("history-view")).toBeVisible();
    await expect(page.getByTestId("history-list")).toHaveAttribute("data-loaded", "12");

    await page.getByTestId("history-clear").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByTestId("history-clear-confirm").click();
    await expect.poll(() => writeCount(state, clearHistoryEp.path, "DELETE")).toBe(1);

    await page.getByTestId("history-clear-progress").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByTestId("history-clear-progress-confirm").click();
    await expect.poll(() => writeCount(state, clearAllProgressEp.path, "DELETE")).toBe(1);

    await page.locator(".history-row").first().getByTestId("history-reset-row").click();
    await expect
      .poll(
        () =>
          state.writes.filter(
            (item) =>
              item.path === clearGalleryProgressEp.path.replace("{id}", "1000") &&
              item.method === "DELETE",
          ).length,
      )
      .toBe(1);

    expect(csp).toEqual([]);
  });

  test("real app routes mount the migrated favourites / favlist / downloads / history views @fav-dl",
    async ({ page }) => {
      const csp = watchConsole(page);
      await installShellMock(page);
      await mockFavDlBackend(page);

      await page.goto("/#/favorites");
      await expect(page.getByTestId("favorites-view")).toBeVisible();
      await expect(page.getByTestId("favorites-table")).toBeVisible();
      await expect(page.getByTestId("favcat-row")).toHaveCount(3);

      await page.goto("/#/favorites/1?page_size=12");
      await expect(page.getByTestId("favlist-view")).toBeVisible();
      await expect(page.getByTestId("favlist-grid")).toBeVisible();

      await page.goto("/#/downloads");
      await expect(page.getByTestId("downloads-view")).toBeVisible();
      await expect(page.locator(".download-item")).toHaveCount(6);

      await page.goto("/#/history");
      await expect(page.getByTestId("history-view")).toBeVisible();
      await expect(page.getByTestId("history-list")).toHaveAttribute("data-loaded", "12");

      expect(csp).toEqual([]);
    });

  test("screenshots: favourites / favlist / downloads / history in dark and light, desktop and mobile @fav-dl",
    async ({ page }) => {
      const csp = watchConsole(page);
      await mockFavDlBackend(page);

      const views: Array<{ view: HarnessView; path: string; testid: string; ready: string }> = [
        { view: "favorites", path: "/favorites", testid: "favorites-view", ready: "favorites-table" },
        {
          view: "favlist",
          path: "/favorites/1?page_size=12",
          testid: "favlist-view",
          ready: "favlist-grid",
        },
        { view: "downloads", path: "/downloads", testid: "downloads-view", ready: "downloads-list" },
        { view: "history", path: "/history", testid: "history-view", ready: "history-list" },
      ];
      const themes: Theme[] = ["dark", "light"];
      const viewports = [
        { width: 1280, height: 900 },
        { width: 390, height: 844 },
      ];

      for (const theme of themes) {
        for (const viewport of viewports) {
          await page.setViewportSize(viewport);
          for (const item of views) {
            await page.goto(harnessUrl({ view: item.view, theme, path: item.path }));
            await expect(page.getByTestId(item.testid)).toBeVisible();
            await expect(page.getByTestId(item.ready)).toBeVisible();
            await page.waitForTimeout(200);
            await shot(page, `${item.view}-${theme}-${viewport.width}`);
          }
        }
      }

      expect(csp).toEqual([]);
    });
});
