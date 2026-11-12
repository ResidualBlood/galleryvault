import { mkdirSync } from "node:fs";
import { createServer as createTcpServer } from "node:net";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { installMaintenanceMock } from "./fixtures/maintenance/mock";

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

function viewUrl(path: string, theme = "dark"): string {
  return `${HARNESS}?theme=${theme}#${path}`;
}

test.describe("maintenance @maintenance", () => {
  test.beforeAll(async () => {
    mkdirSync(SHOTS, { recursive: true });
    const port = await freePort();
    vite = await createServer({
      root: PROJECT_ROOT,
      logLevel: "error",
      server: { host: "127.0.0.1", port, strictPort: true },
    });
    await vite.listen();
    HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/maintenance/harness.html`;
  });

  test.afterAll(async () => {
    await vite?.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.context().addCookies([
      { name: "galleryvault_csrf", value: "test-csrf", url: HARNESS },
    ]);
  });

  test("updates: list, status, update, ignore and confirmed delete", async ({ page }) => {
    const csp = watchConsole(page);
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/updates"));
    await expect(page.getByTestId("updates-view")).toBeVisible();
    await expect(page.getByTestId("updates-row-1")).toContainText("Updated Alpha");
    await expect(page.getByTestId("updates-status")).toContainText("3");

    await page.getByTestId("updates-select-1").check();
    await page.getByTestId("updates-update").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" && request.path === "/api/updates/update",
          ).at(-1)?.body,
      )
      .toMatchObject({ ids: [1] });

    await page.getByTestId("updates-select-2").check();
    await page.getByTestId("updates-ignore").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" && request.path === "/api/updates/ignore",
          ).length,
      )
      .toBe(1);

    await page.getByTestId("updates-state-failed").click();
    await expect(page).toHaveURL(/state=failed/);
    await expect(page.getByTestId("updates-row-3")).toBeVisible();
    await page.getByTestId("updates-select-3").check();
    await page.getByTestId("updates-delete").click();
    await expect(page.getByTestId("updates-delete-dialog")).toBeVisible();
    await page.getByTestId("confirm-accept").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" && request.path === "/api/updates/delete",
          ).at(-1)?.body,
      )
      .toMatchObject({ ids: [3] });

    expect(csp).toEqual([]);
  });

  test("updates ignored: restore selected and single rows", async ({ page }) => {
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/updates/ignored"));
    await expect(page.getByTestId("updates-ignored-view")).toBeVisible();
    await expect(page.getByTestId("updates-ignored-4")).toContainText("Ignored Delta");

    await page
      .getByTestId("updates-ignored-4")
      .locator('input[type="checkbox"]')
      .check();
    await page.getByTestId("updates-unignore-selected").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" && request.path === "/api/updates/unignore",
          ).at(-1)?.body,
      )
      .toMatchObject({ ids: [4] });
  });

  test("library duplicates: confirm keep, delete others and set status", async ({ page }) => {
    const csp = watchConsole(page);
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/duplicates"));
    await expect(page.getByTestId("duplicates-view")).toBeVisible();
    await expect(page.getByTestId("duplicates-group-9001")).toContainText("Alpha Copy");

    await page.getByTestId("duplicates-keep-delete-copy-b").click();
    await expect(page.getByTestId("duplicates-confirm")).toBeVisible();
    await page.getByTestId("confirm-accept").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" &&
              request.path === "/api/scan/duplicates/9001/resolve",
          ).at(-1)?.body,
      )
      .toMatchObject({ path: "/library/alpha.cbz", delete_others: true });

    await page.getByTestId("duplicates-dismiss-9002").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" &&
              request.path === "/api/scan/duplicates/9002/open",
          ).length,
      )
      .toBe(1);

    expect(csp).toEqual([]);
  });

  test("favorite duplicates: scan, unfavorite + delete and ignore", async ({ page }) => {
    const csp = watchConsole(page);
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/duplicates/favorites"));
    await expect(page.getByTestId("dupfav-view")).toBeVisible();
    await expect(page.getByTestId("dupfav-group-fav-group-1")).toBeVisible();

    await page.getByTestId("dupfav-scan").click();
    await expect.poll(() => state.favoriteScans).toBe(1);

    await page.getByTestId("dupfav-select-3002").check();
    await page.getByTestId("dupfav-unfav-delete").click();
    await expect(page.getByTestId("dupfav-confirm")).toBeVisible();
    await page.getByTestId("confirm-accept").click();
    await expect.poll(() => state.removals.at(-1)).toEqual({
      gids: [3002],
      deleteLocal: true,
    });

    await page.getByTestId("dupfav-select-3001").check();
    await page.getByTestId("dupfav-ignore").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" &&
              request.path === "/api/favorites/duplicates/ignore",
          ).at(-1)?.body,
      )
      .toMatchObject({ key: "fav-group-1" });

    expect(csp).toEqual([]);
  });

  test("ignored favorite duplicates: restore selected", async ({ page }) => {
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/favorites/ignored"));
    await expect(page.getByTestId("favignored-view")).toBeVisible();
    await expect(page.getByTestId("favignored-item-4001")).toBeVisible();

    await page.getByTestId("favignored-select-0").check();
    await page.getByTestId("favignored-restore-selected").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "DELETE" &&
              request.path === "/api/favorites/duplicates/ignore",
          ).at(-1)?.query.get("key"),
      )
      .toBe("ignored-fav-1");
  });

  test("cross-gid duplicates: safe links, confirmed remove and recompute", async ({ page }) => {
    const csp = watchConsole(page);
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/duplicates/cross-gid"));
    await expect(page.getByTestId("dupxgid-view")).toBeVisible();
    await expect(page.getByTestId("dupxgid-item-5001")).toBeVisible();

    const link = page.getByTestId("dupxgid-link-5002");
    await expect(link).toHaveAttribute("href", "#");
    expect(await page.locator('a[href^="javascript:"]').count()).toBe(0);

    await page.getByTestId("dupxgid-select-5002").check();
    await page.getByTestId("dupxgid-unfav-delete").click();
    await expect(page.getByTestId("dupxgid-confirm")).toBeVisible();
    await page.getByTestId("confirm-accept").click();
    await expect.poll(() => state.removals.at(-1)).toEqual({
      gids: [5002],
      deleteLocal: true,
    });

    await page.getByTestId("dupxgid-recompute").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" &&
              request.path === "/api/library/duplicates/cross-gid/refresh",
          ).length,
      )
      .toBe(1);

    expect(csp).toEqual([]);
  });

  test("recycle: restore, confirmed purge with files and expunged redownload", async ({
    page,
  }) => {
    const csp = watchConsole(page);
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/recycle"));
    await expect(page.getByTestId("recycle-view")).toBeVisible();
    await expect(page.getByTestId("recycle-item-21")).toContainText("Trash One");

    await page.getByTestId("recycle-select-21").check();
    await page.getByTestId("recycle-restore").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" && request.path === "/api/galleries/restore",
          ).at(-1)?.body,
      )
      .toMatchObject({ ids: [21] });

    await page.getByTestId("recycle-select-22").check();
    await page.getByTestId("recycle-purge").click();
    await expect(page.getByTestId("recycle-purge-dialog")).toBeVisible();
    await page.getByTestId("recycle-delete-files").check();
    await page.getByTestId("confirm-accept").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" && request.path === "/api/galleries/purge",
          ).at(-1)?.body,
      )
      .toMatchObject({ ids: [22], delete_files: true });

    await page.getByTestId("recycle-tab-expunged").click();
    await expect(page).toHaveURL(/tab=expunged/);
    await expect(page.getByTestId("recycle-item-31")).toContainText("Expunged One");
    await page.getByTestId("recycle-select-31").check();
    await page.getByTestId("recycle-redownload").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" &&
              request.path === "/api/galleries/expunged/redownload",
          ).at(-1)?.body,
      )
      .toMatchObject({ ids: [31] });

    expect(csp).toEqual([]);
  });

  test("integrity: scan, select all and repair", async ({ page }) => {
    const csp = watchConsole(page);
    const state = await installMaintenanceMock(page);

    await page.goto(viewUrl("/integrity"));
    await expect(page.getByTestId("integrity-view")).toBeVisible();
    await expect(page.getByTestId("integrity-item-41")).toContainText("Integrity One");

    await page.getByTestId("integrity-select-all").click();
    await page.getByTestId("integrity-repair").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" &&
              /^\/api\/galleries\/\d+\/redownload$/.test(request.path),
          ).length,
      )
      .toBe(2);

    await page.getByTestId("integrity-scan").click();
    await expect
      .poll(
        () =>
          state.requests.filter(
            (request) =>
              request.method === "POST" &&
              request.path === "/api/galleries/integrity/scan",
          ).length,
      )
      .toBe(1);

    expect(csp).toEqual([]);
  });

  test("screenshots cover every view in dark/light and desktop/mobile", async ({ page }) => {
    const csp = watchConsole(page);
    await installMaintenanceMock(page);

    const views = [
      { name: "updates", path: "/updates", ready: "updates-row-1" },
      { name: "updates-ignored", path: "/updates/ignored", ready: "updates-ignored-4" },
      { name: "duplicates", path: "/duplicates", ready: "duplicates-group-9001" },
      {
        name: "duplicates-favorites",
        path: "/duplicates/favorites",
        ready: "dupfav-group-fav-group-1",
      },
      {
        name: "duplicates-cross-gid",
        path: "/duplicates/cross-gid",
        ready: "dupxgid-item-5001",
      },
      { name: "recycle", path: "/recycle", ready: "recycle-item-21" },
      { name: "integrity", path: "/integrity", ready: "integrity-item-41" },
    ] as const;
    const themes = ["dark", "light"] as const;
    const viewports = [
      { width: 1280, height: 900 },
      { width: 390, height: 844 },
    ];

    for (const view of views) {
      for (const theme of themes) {
        for (const viewport of viewports) {
          await page.setViewportSize(viewport);
          await page.goto(viewUrl(view.path, theme));
          await expect(page.getByTestId(view.ready)).toBeVisible();
          await page.screenshot({
            path: join(SHOTS, `maintenance-${view.name}-${theme}-${viewport.width}.png`),
            fullPage: true,
          });
        }
      }
    }

    expect(csp).toEqual([]);
  });
});
