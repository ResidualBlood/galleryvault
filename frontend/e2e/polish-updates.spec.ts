import { mkdirSync } from "node:fs";
import { createServer as createTcpServer } from "node:net";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { installMaintenanceMock } from "./fixtures/maintenance/mock";
import {
  updatesEp,
  updatesIgnoredEp,
  updatesScanEp,
  updatesStatusEp,
} from "@/api/updates";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  shotMatrix,
} from "./support/polish";

/**
 * po-updates polish gate (batch 23).
 *
 * Closes the sixteen audit defects of the updates module:
 *
 *   - UP-01/UI-01 the empty states explain themselves and offer a primary exit;
 *   - UP-02 scan is the one filled action until a row is selected;
 *   - UP-03 scan + status filter share one Toolbar / one control ladder;
 *   - UP-04/UI-02 disabled buttons use the M3 layered disabled treatment;
 *   - UP-05 selection uses the shared 40px Checkbox;
 *   - UP-06 the ignored entry lives in the page header actions;
 *   - UP-07 the last scan time is always rendered, the count is a chip;
 *   - UP-08 filter labels are unambiguous, "全部" is first, aria-label is i18n;
 *   - UP-09 the six-column table becomes card rows below 840px;
 *   - UP-10 is deferred to the shared EmptyState (po-final-gate);
 *   - UP-11 the footer is the shared Pager;
 *   - UI-03 `/updates/ignored` is a child route so the drawer keeps "更新" active;
 *   - UI-04/UI-05 the ignored view is a PageHeader with a back IconButton.
 */

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

function watchCsp(page: Page): string[] {
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

function harnessUrl(path = "/updates", theme = "dark"): string {
  return `${HARNESS}?theme=${theme}#${path}`;
}

/** Geometry of one toolbar row, including the segmented control wrapper. */
async function toolbarMetrics(page: Page, testid: string) {
  return page.evaluate((id) => {
    const toolbar = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    if (!toolbar) return null;
    const nodes = [
      ...toolbar.querySelectorAll<HTMLElement>(
        '[data-gv-control], .segmented, input:not([type="hidden"])',
      ),
    ]
      .map((node) => node.getBoundingClientRect())
      .filter((rect) => rect.width > 1 && rect.height > 1);
    return {
      box: toolbar.getBoundingClientRect().toJSON(),
      heights: nodes.map((rect) => Math.round(rect.height * 10) / 10),
      centers: nodes.map((rect) => Math.round((rect.top + rect.height / 2) * 10) / 10),
      rights: nodes.map((rect) => Math.round(rect.right * 10) / 10),
    };
  }, testid);
}

async function emptyUpdates(page: Page): Promise<void> {
  await page.route(
    (url) => url.pathname === updatesEp.path,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ total: 0, page: 1, page_size: 24, state: "active", items: [] }),
      });
    },
  );
  await page.route(
    (url) => url.pathname === updatesStatusEp.path,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          detecting: false,
          last_detected_at: null,
          last_run: null,
          last_error: null,
          last_found: 0,
          counts: { pending: 0, downloading: 0, failed: 0, ignored: 0 },
        }),
      });
    },
  );
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
  HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/maintenance/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

test("updates toolbar is one aligned row and the table uses the shared header @polish-updates", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await installMaintenanceMock(page);
  await page.goto(harnessUrl());
  await expect(page.getByTestId("updates-row-1")).toBeVisible();

  await expectNoGlyphIcons(page, { selector: "[data-testid='updates-view']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='updates-header']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='updates-toolbar']" });

  // UP-03: scan stays on the lg ladder step; the segmented filter is the chip
  // step and both share one centre line in one toolbar row.
  await expectControlHeights(page.getByTestId("updates-toolbar").locator("[data-gv-control]"), 40);
  const toolbar = await toolbarMetrics(page, "updates-toolbar");
  expect(toolbar).toBeTruthy();
  expect(Math.max(...toolbar!.centers) - Math.min(...toolbar!.centers)).toBeLessThanOrEqual(1);
  const segmentedBox = await page.getByTestId("updates-state-filter").boundingBox();
  expect(segmentedBox!.height).toBeCloseTo(38, 0);

  // UP-08: "全部" first, one label per state.
  const labels = await page
    .getByTestId("updates-state-filter")
    .locator(".segmented__label")
    .allInnerTexts();
  expect(labels).toEqual(["全部", "有更新", "待下载", "下载中", "失败"]);
  await expect(page.getByTestId("updates-state-filter")).toHaveAttribute("aria-label", "按状态筛选");

  // UP-09: desktop keeps the six-column table; the header matches GalleryTable
  // (label-small, 11px on the 4px grid).
  const table = page.getByTestId("updates-table");
  await expect(table).toBeVisible();
  const header = await table.locator("thead th").last().evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      fontSize: Number.parseFloat(style.fontSize),
      height: Math.round(node.getBoundingClientRect().height * 10) / 10,
    };
  });
  const labelSmall = await page.evaluate(() =>
    Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--gv-type-label-small-size"),
    ),
  );
  const rootFont = await page.evaluate(() =>
    Number.parseFloat(getComputedStyle(document.documentElement).fontSize),
  );
  expect(header.fontSize).toBeCloseTo(labelSmall * rootFont, 0);
  expect(header.height).toBeCloseTo(40, 0);

  // UP-05: the row selection control is the shared Checkbox (44px hit area).
  const selectOne = page.getByTestId("updates-select-1");
  const selectBox = await selectOne.boundingBox();
  expect(selectBox!.height).toBeGreaterThanOrEqual(40);
  await selectOne.check();
  const selection = page.getByTestId("updates-selection");
  await expect(selection).toBeVisible();
  await expect(selection).toContainText("已选 1 项");
  for (const action of [
    "updates-update",
    "updates-update-original",
    "updates-archive",
    "updates-ignore",
  ]) {
    await expect(page.getByTestId(action)).toBeVisible();
  }
  await page.screenshot({ path: join(SHOTS, "updates-selection-dark-1280.png") });

  // UP-11: the shared Pager replaces PagerBar; there is no `.pager-bar` class.
  await expect(page.locator(".pager-bar")).toHaveCount(0);

  // The failed bucket exposes the danger action last, after selecting a row.
  await page
    .getByTestId("updates-state-filter")
    .locator('[data-segmented-value="failed"]')
    .click();
  await expect(page).toHaveURL(/state=failed/);
  await page.getByTestId("updates-select-3").check();
  const danger = page.getByTestId("updates-delete");
  await expect(danger).toBeVisible();
  const slots = await page.evaluate(() => {
    const node = document.querySelector('[data-testid="updates-delete"]');
    return {
      inDangerSlot: Boolean(node?.closest(".selection__danger")),
      dangerClass: node?.className ?? "",
    };
  });
  expect(slots.inDangerSlot).toBe(true);
  expect(slots.dangerClass).toContain("btn--danger");
  await page.screenshot({ path: join(SHOTS, "updates-failed-selection-dark-1280.png") });

  expect(csp).toEqual([]);
});

test("updates footer is the shared Pager @polish-updates", async ({ page }) => {
  const csp = watchCsp(page);
  await installMaintenanceMock(page);
  await page.route(
    (url) => url.pathname === updatesEp.path,
    async (route) => {
      const request = new URL(route.request().url());
      const pageNumber = Number(request.searchParams.get("page") ?? "1");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total: 72,
          page: pageNumber,
          page_size: 24,
          state: request.searchParams.get("state") ?? "active",
          items: [
            {
              id: 1,
              gallery_id: 11,
              old_gid: 1001,
              new_gid: 2001,
              title: "Updated Alpha",
              favcat: 3,
              favcat_name: "Favorites",
              status: "pending",
              error_message: null,
              detected_at: "2026-11-01T10:00:00Z",
              updated_at: "2026-11-01T10:00:00Z",
            },
          ],
        }),
      });
    },
  );
  await page.goto(harnessUrl());
  const pager = page.getByTestId("updates-pager");
  await expect(pager).toBeVisible();
  await expectNoGlyphIcons(page, { selector: "[data-testid='updates-pager']" });
  await expectControlHeights(pager.locator("button, input, select"), 36);
  await expect(pager.locator('[data-pager="prev"] svg')).toHaveCount(1);
  await expect(pager.locator('[data-pager="next"] svg')).toHaveCount(1);
  await expect(pager.getByRole("button", { name: "第 2 页" })).toBeVisible();

  await pager.locator('[data-pager="next"]').click();
  await expect(page).toHaveURL(/page=2/);
  await page.screenshot({ path: join(SHOTS, "updates-pager-dark-1280.png") });

  // UP-11: no legacy PagerBar class is rendered anywhere on the page.
  await expect(page.locator(".pager-bar")).toHaveCount(0);
  expect(csp).toEqual([]);
});

test("updates becomes card rows at 390 with no horizontal overflow @polish-updates", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await installMaintenanceMock(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(harnessUrl());
  await expect(page.getByTestId("updates-row-1")).toBeVisible();

  await expectNoHorizontalOverflow(page);
  await expectNoGlyphIcons(page, { selector: "[data-testid='updates-view']" });

  // UP-09: the same six-column table is re-flowed into a card row; the table
  // header is hidden and no column is pushed off-screen.
  await expect(page.getByTestId("updates-table").locator("thead")).toBeHidden();
  const row = await page.getByTestId("updates-row-1").evaluate((node) => {
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    const container = node.closest(".updates")?.getBoundingClientRect();
    return {
      display: style.display,
      width: Math.round(rect.width),
      right: Math.round(rect.right),
      containerWidth: Math.round(container?.width ?? 0),
    };
  });
  expect(row.display).toBe("grid");
  expect(row.width).toBeLessThanOrEqual(row.containerWidth + 1);
  expect(row.right).toBeLessThanOrEqual(390);

  // The segmented filter scrolls on one line rather than wrapping.
  const segmentTops = await page
    .getByTestId("updates-state-filter")
    .locator(".segmented__item")
    .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().top)));
  expect(Math.max(...segmentTops) - Math.min(...segmentTops)).toBeLessThanOrEqual(1);

  // Selection stays usable at 390 and both bars stay one line high.
  await page.getByTestId("updates-select-1").check();
  await expect(page.getByTestId("updates-selection")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: join(SHOTS, "updates-selection-dark-390.png") });
  expect(csp).toEqual([]);
});

test("updates empty state explains the scan and keeps the last scan time @polish-updates", async ({
  page,
}) => {
  const csp = watchCsp(page);
  const state = await installMaintenanceMock(page);
  await emptyUpdates(page);
  await page.goto(harnessUrl());
  const empty = page.getByTestId("updates-empty");
  await expect(empty).toBeVisible();

  // UP-01: title + explanation + one clickable primary action.
  await expect(empty.locator(".state__title")).toHaveText("没有检测到有更新的画廊。");
  await expect(empty.locator(".state__body")).not.toBeEmpty();
  const action = page.getByTestId("updates-empty-action");
  await expect(action).toBeVisible();
  await expect(action).toBeEnabled();
  await expect(action).toHaveText("立即检测");

  // UP-07: the last scan line is rendered even before the first scan.
  await expect(page.getByTestId("updates-status")).toContainText("上次检测：—");
  await expect(page.getByTestId("updates-status")).toContainText("共 0 项");

  const before = state.requests.filter((request) => request.path === updatesScanEp.path).length;
  await action.click();
  await expect
    .poll(
      () =>
        state.requests.filter((request) => request.path === updatesScanEp.path).length,
    )
    .toBe(before + 1);

  await expectNoGlyphIcons(page, { selector: "[data-testid='updates-view']" });
  await expectNoHorizontalOverflow(page);
  const shots = await shotMatrix(page, "updates-empty");
  expect(shots.files).toHaveLength(4);
  expect(csp).toEqual([]);
});

test("ignored updates is a secondary view with a back exit @polish-updates", async ({ page }) => {
  const csp = watchCsp(page);
  await installMaintenanceMock(page);
  await page.goto(harnessUrl("/updates/ignored"));
  await expect(page.getByTestId("updates-ignored-4")).toBeVisible();

  // UI-04/UI-05: PageHeader owns the heading and the 40px back IconButton;
  // there is no duplicated eyebrow or hand-styled text link.
  const header = page.getByTestId("updates-ignored-header");
  await expect(header.locator("h1")).toHaveText("已忽略的更新");
  const back = header.getByRole("button", { name: "返回更新画廊" });
  await expect(back).toBeVisible();
  const backBox = await back.boundingBox();
  expect(backBox!.width).toBeGreaterThanOrEqual(40);
  expect(backBox!.height).toBeGreaterThanOrEqual(40);
  await expect(page.getByTestId("updates-ignored-view")).not.toContainText("GALLERY UPDATES");

  await back.click();
  await expect(page).toHaveURL(/#\/updates$/);

  // UI-01: the empty state offers the exit back to the updates page.
  await page.route(
    (url) => url.pathname === updatesIgnoredEp.path,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ total: 0, page: 1, page_size: 500, state: "ignored", items: [] }),
      });
    },
  );
  await page.goto(harnessUrl("/updates/ignored"));
  const empty = page.getByTestId("updates-ignored-empty");
  await expect(empty).toBeVisible();
  await expect(empty.locator(".state__body")).not.toBeEmpty();
  const exit = page.getByTestId("updates-ignored-empty-action");
  await expect(exit).toHaveText("返回更新画廊");
  await exit.click();
  await expect(page).toHaveURL(/#\/updates$/);

  await expectNoGlyphIcons(page, { selector: "[data-testid='updates-view']" });
  expect(csp).toEqual([]);
});

test("@polish-updates four-variant screenshots for updates and ignored", async ({ page }) => {
  test.setTimeout(180_000);
  const csp = watchCsp(page);
  await installMaintenanceMock(page);

  await page.goto(harnessUrl());
  await expect(page.getByTestId("updates-row-1")).toBeVisible();
  const updates = await shotMatrix(page, "updates");
  expect(updates.files).toHaveLength(4);

  await page.goto(harnessUrl("/updates/ignored"));
  await expect(page.getByTestId("updates-ignored-4")).toBeVisible();
  const ignored = await shotMatrix(page, "updates-ignored");
  expect(ignored.files).toHaveLength(4);

  expect(csp).toEqual([]);
});
