import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { mockFavDlBackend } from "./fixtures/fav-dl/mock";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
  freePort,
  watchCsp,
} from "./support/polish";

/**
 * po-favorites polish gate (batch 22).
 *
 * Closes the 20 audit defects of the favourites module:
 *
 *   - FV-01/02 the folder table puts Switch / Select / TextField / Button on the
 *     md ladder step with one centre line;
 *   - FV-03/04/07 one filled action at most, real buttons instead of a
 *     hand-styled link, secondary actions collapse below 600px;
 *   - FV-05/06/08 no English eyebrow, units on the control, Skeleton loading;
 *   - FL-01/12 eleven flat targets become toolbar + SelectionBar (selection
 *     only), danger action last;
 *   - FL-02/03/05 filtered search row is one step, labels say what they are and
 *     the advanced panel collapses behind a counted FilterButton;
 *   - FL-04 the folder heading never repeats "#N";
 *   - FL-06/07/08 the single-folder grid is the shared GalleryCard (same root
 *     class as the library) with 24px tag chips and a 40px checkbox hit area;
 *   - FL-09/10/11 icon pagination, one Pager and one count position.
 */

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

let vite: ViteDevServer;
let HARNESS = "";



function harnessUrl(options: { view: "favorites" | "favlist"; path?: string; theme?: string }): string {
  const params = new URLSearchParams();
  params.set("view", options.view);
  params.set("theme", options.theme ?? "dark");
  if (options.path) params.set("path", options.path);
  return `${HARNESS}?${params.toString()}`;
}

async function openFolder(page: Page, path = "/favorites/1"): Promise<void> {
  await page.goto(harnessUrl({ view: "favlist", path }));
  await expect(page.getByTestId("favlist-view")).toBeVisible();
}

async function openDirectory(page: Page): Promise<void> {
  await page.goto(harnessUrl({ view: "favorites" }));
  await expect(page.getByTestId("favorites-view")).toBeVisible();
  await expect(page.getByTestId("favorites-table")).toBeVisible();
}

/** Per-row geometry of the folder table: heights and centre lines. */
async function folderRowMetrics(page: Page) {
  return page.evaluate(() => {
    const rows = [...document.querySelectorAll<HTMLElement>('[data-testid="favcat-row"]')];
    return rows.map((row) => {
      const box = (selector: string) =>
        [...row.querySelectorAll<HTMLElement>(selector)]
          .map((node) => node.getBoundingClientRect())
          .filter((rect) => rect.width > 1 && rect.height > 1)
          .map((rect) => ({
            height: Math.round(rect.height * 10) / 10,
            center: Math.round((rect.top + rect.height / 2) * 10) / 10,
          }));
      return {
        controls: box('select, input, button:not([role="switch"])'),
        switches: box('[role="switch"]'),
      };
    });
  });
}

/** Geometry of one toolbar row, including the SegmentedControl wrapper. */
async function toolbarMetrics(page: Page, testid: string) {
  return page.evaluate((id) => {
    const toolbar = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    if (!toolbar) return null;
    const nodes = [
      ...toolbar.querySelectorAll<HTMLElement>(
        '[data-gv-control], .segmented, select, input:not([type="hidden"])',
      ),
    ]
      .map((node) => node.getBoundingClientRect())
      .filter((rect) => rect.width > 1 && rect.height > 1);
    return {
      box: toolbar.getBoundingClientRect().toJSON(),
      heights: nodes.map((rect) => Math.round(rect.height * 10) / 10),
      centers: nodes.map((rect) => Math.round((rect.top + rect.height / 2) * 10) / 10),
      tops: nodes.map((rect) => Math.round(rect.top * 10) / 10),
    };
  }, testid);
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

test("folder table keeps every inline control on the md step @polish-favorites", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await mockFavDlBackend(page);
  await openDirectory(page);

  await expectNoGlyphIcons(page, { selector: "[data-testid='favorites-view']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='favorites-toolbar']" });
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='favorites-toolbar']",
    requireRows: true,
    tolerance: 1,
  });

  const rows = await folderRowMetrics(page);
  expect(rows.length).toBe(3);
  for (const row of rows) {
    expect(row.controls.length).toBeGreaterThanOrEqual(3);
    const heights = row.controls.map((entry) => entry.height);
    const centers = [...row.controls, ...row.switches].map((entry) => entry.center);
    const switchHeights = row.switches.map((entry) => entry.height);
    // FV-01: Select / TextField / Button share one step, the switch keeps its
    // 52x32 track, and every control shares a single centre line.
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
    expect(heights[0]).toBeCloseTo(36, 0);
    expect(switchHeights.every((height) => Math.abs(height - 32) <= 1)).toBe(true);
    expect(Math.max(...centers) - Math.min(...centers)).toBeLessThanOrEqual(1);
  }

  // FV-06: the unit lives on the control, not in the column header.
  const interval = page.locator('[data-testid="favcat-row"]').first().getByTestId("favcat-interval");
  await expect(interval).toContainText("分钟");
  const header = page.locator(".favcats__row--head");
  await expect(header).not.toContainText("（分钟）");

  // FV-02: one type scale in the row — every control uses body medium.
  const fontSizes = await page.evaluate(() => {
    const row = document.querySelector('[data-testid="favcat-row"]');
    if (!row) return [];
    return [...row.querySelectorAll<HTMLElement>("select, input")]
      .map((node) => Number.parseFloat(getComputedStyle(node).fontSize))
      .filter((size) => Number.isFinite(size));
  });
  expect(new Set(fontSizes).size).toBe(1);

  // FV-04: "gallery updates" is a link, not a hand-styled fake button.
  const updates = page.locator(".favcats__link");
  await expect(updates).toHaveAttribute("href", /\/updates$/);
  await expect(page.getByRole("button", { name: "更新画廊" })).toHaveCount(0);

  // FV-05: no English eyebrow — the shared PageHeader owns the heading.
  await expect(page.getByTestId("favorites-header").locator("h1")).toHaveText("收藏夹监控");
  await expect(page.getByTestId("favorites-view")).not.toContainText("EXHENTAI FOLDERS");

  expect(csp).toEqual([]);
});

test("folder table stacks into cards at 390 and shows a skeleton while loading @polish-favorites", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await mockFavDlBackend(page);

  // FV-08: a real Skeleton replaces the old "加载中…" paragraph. The
  // categories response is held until the loading state is captured.
  let releaseCategories: () => void = () => {};
  const categoriesGate = new Promise<void>((resolve) => {
    releaseCategories = () => resolve();
  });
  await page.route("**/api/favorites/categories", async (route) => {
    await categoriesGate;
    await route.fallback();
  });
  await page.goto(harnessUrl({ view: "favorites" }));
  await expect(page.getByTestId("favorites-loading")).toBeVisible();
  await expect(page.getByTestId("favorites-loading").locator(".skeleton")).toHaveCount(4);
  await page.screenshot({ path: join(SHOTS, "favorites-loading-dark-1280.png") });
  releaseCategories();
  await expect(page.getByTestId("favorites-table")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  // FV-07: the secondary actions collapse below 600px, only the primary stays.
  await expect(page.getByTestId("favorites-toolbar")).toBeVisible();
  await expect(page.getByTestId("favorites-check-all")).toBeVisible();
  await expect(page.getByTestId("favorites-sync")).toHaveCount(0);
  await expect(page.getByTestId("favorites-download-missing")).toHaveCount(0);
  await expect(
    page.getByTestId("favorites-toolbar").getByTestId("gv-toolbar-more-trigger"),
  ).toBeVisible();
  // The stacked card keeps the two-line structure from the audit: name + switch
  // on the first line, mode / interval / action on the last.
  const stacked = await page.evaluate(() => {
    const row = document.querySelector<HTMLElement>('[data-testid="favcat-row"]');
    if (!row) return null;
    const center = (selector: string) => {
      const node = row.querySelector<HTMLElement>(selector);
      const rect = node?.getBoundingClientRect();
      return rect ? Math.round((rect.top + rect.height / 2) * 10) / 10 : Number.NaN;
    };
    return {
      name: center(".favcats__cell--name"),
      toggle: center(".favcats__cell--switch"),
      mode: center(".favcats__cell--mode"),
      interval: center(".favcats__cell--interval"),
      action: center(".favcats__cell--action"),
    };
  });
  expect(stacked).toBeTruthy();
  expect(Math.abs(stacked!.name - stacked!.toggle)).toBeLessThanOrEqual(4);
  expect(Math.abs(stacked!.mode - stacked!.interval)).toBeLessThanOrEqual(1);
  expect(stacked!.action).toBeGreaterThan(stacked!.mode);
  // The interval keeps its four digits visible next to the unit.
  const intervalValue = await page
    .locator('[data-testid="favcat-row"]')
    .last()
    .getByTestId("favcat-interval")
    .locator("input")
    .inputValue();
  expect(intervalValue).toBe("1440");
  await expect(page.locator(".favcats__row--head")).toBeHidden();
  expect(csp).toEqual([]);
});

test("single folder toolbar is one aligned row and hides bulk actions until selection @polish-favorites", async ({
  page,
}) => {
  const csp = watchCsp(page);
  const state = await mockFavDlBackend(page);
  await openFolder(page);

  await expectNoGlyphIcons(page, { selector: "[data-testid='favlist-view']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='favlist-toolbar']" });

  // FL-01: one row at 1280, no wrapping.
  const toolbar = await toolbarMetrics(page, "favlist-toolbar");
  expect(toolbar).toBeTruthy();
  const tops = toolbar!.tops;
  expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(1);
  expect(toolbar!.box.height).toBeLessThanOrEqual(56);

  // Every field / button is on the lg step; the segmented wrapper is the same
  // 40px step (C17) and shares the centre line (FL-02).
  await expectControlHeights(
    page.getByTestId("favlist-toolbar").locator("[data-gv-control]"),
    40,
  );
  expect(Math.max(...toolbar!.centers) - Math.min(...toolbar!.centers)).toBeLessThanOrEqual(1);
  const segmented = await page.getByTestId("favlist-state").boundingBox();
  expect(segmented!.height).toBeCloseTo(40, 0);

  // The persistent drawer eats 264px in the real shell: 1024 still fits one row.
  await page.setViewportSize({ width: 1024, height: 900 });
  const narrower = await toolbarMetrics(page, "favlist-toolbar");
  expect(narrower!.box.height).toBeLessThanOrEqual(56);
  await page.setViewportSize({ width: 1280, height: 900 });

  // FL-12: nothing to act on before selecting, and the danger action is last.
  await expect(page.getByTestId("favlist-selection")).toHaveCount(0);
  await expect(page.getByTestId("favlist-download")).toHaveCount(0);
  await expect(page.getByTestId("favlist-remove")).toHaveCount(0);

  const first = page.locator(".gallery-card").first();
  await first.locator('input[type="checkbox"]').check();
  const selection = page.getByTestId("favlist-selection");
  await expect(selection).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "favlist-selection-dark-1280.png") });
  await expect(selection).toContainText("已选 1 本");
  await expect(page.getByTestId("favlist-download")).toContainText("(1)");

  const order = await selection.evaluate((node) => {
    const danger = node.querySelector('[data-testid="favlist-remove"]');
    const actions = [...node.querySelectorAll("button")];
    const clear = node.querySelector('[data-testid="gv-selection-clear"]');
    const bulk = actions.filter((button) => button !== clear);
    return {
      dangerClass: danger?.className ?? "",
      dangerIndex: bulk.indexOf(danger as HTMLButtonElement),
      lastIndex: bulk.length - 1,
      inDangerSlot: Boolean(danger?.closest(".selection__danger")),
    };
  });
  expect(order.dangerClass).toContain("btn--danger");
  expect(order.inDangerSlot).toBe(true);
  expect(order.dangerIndex).toBe(order.lastIndex);

  // FL-03 / FL-05: labelled filters and a counted disclosure.
  await page.getByTestId("favlist-advanced-toggle").click();
  await expect(page.getByTestId("favlist-advanced-toggle")).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await expect(page.getByTestId("favlist-category").locator(".select-field__label")).toHaveText(
    "分类",
  );
  await expect(page.getByTestId("favlist-advanced")).toBeVisible();
  await expect(page.getByTestId("gv-filter-badge")).toHaveCount(0);
  await page.screenshot({ path: join(SHOTS, "favlist-filters-dark-1280.png") });

  // FL-02: the advanced grid keeps every float-free row aligned; clear filters
  // live in the panel footer instead of the search row.
  await expect(page.getByTestId("favlist-clear")).toBeVisible();
  const advancedHeights = await page.evaluate(() => {
    const panel = document.querySelector('[data-testid="favlist-advanced"]');
    if (!panel) return [];
    return [...panel.querySelectorAll<HTMLElement>("input, select")].map(
      (node) => Math.round(node.getBoundingClientRect().height * 10) / 10,
    );
  });
  expect(new Set(advancedHeights)).toEqual(new Set([40]));

  // FL-10: the footer is the shared Pager (36px controls + one select).
  await expect(page.getByTestId("favlist-pager")).toBeVisible();
  await expectNoGlyphIcons(page, { selector: "[data-testid='favlist-pager']" });
  await expect(page.getByTestId("favlist-pager").locator('[data-pager="prev"] svg')).toHaveCount(1);
  await expectControlHeights(
    page.getByTestId("favlist-pager").locator('button, input, select'),
    36,
  );

  // FL-06/07: the favourites grid is the shared card, tag chips are 24px.
  await page.locator('[data-view-mode="list"]').click();
  const listTags = page.locator(".gallery-list-row__tags .tag-chip");
  await expect(listTags.first()).toBeVisible();
  const chipBox = await listTags.first().boundingBox();
  expect(chipBox!.height).toBeCloseTo(24, 0);

  // FL-04: the heading never repeats the raw slot id.
  const heading = await page.getByTestId("favlist-header").locator("h1").innerText();
  expect(heading).not.toMatch(/#\d+/);
  await expect(page.getByTestId("favlist-header").locator("h1")).toHaveText("Doujinshi");

  // The list request asks for every tag (be-list-tags `tags_limit`).
  await expect
    .poll(() => state.favoriteItemRequests.at(-1)?.get("tags_limit"))
    .toBe("0");

  expect(csp).toEqual([]);
});

test("single folder switches grid / list / table and remembers it per page @polish-favorites", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await mockFavDlBackend(page);
  await openFolder(page);

  const grid = page.getByTestId("favlist-grid");
  await expect(grid).toHaveAttribute("data-mode", "grid");
  expect(await grid.locator(".gallery-card").count()).toBeGreaterThan(0);
  await expect(grid.locator(".gallery-card__cover").first()).toBeVisible();
  await expect(grid.locator(".badge-strip").first()).toBeVisible();

  for (const mode of ["list", "table"] as const) {
    await page.locator(`[data-view-mode="${mode}"]`).click();
    await expect(grid).toHaveAttribute("data-mode", mode);
  }
  await expect(page.locator(".gallery-table-row").first()).toBeVisible();
  await expect(
    page.locator(".gallery-table-row__cell--tags .tag-chip").first(),
  ).toBeVisible();

  const stored = await page.evaluate(() => localStorage.getItem("gv_view_mode"));
  expect(JSON.parse(stored ?? "{}")).toMatchObject({ favlist: "table" });

  // Narrowing the window falls back to list but keeps the stored preference.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(grid).toHaveAttribute("data-mode", "list");
  await expectNoHorizontalOverflow(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(grid).toHaveAttribute("data-mode", "table");

  // Table sorting maps the title header to the favourites `order_by` set.
  await page.locator(".gallery-table__sort").first().click();
  await expect.poll(() => page.evaluate(() => window.location.hash)).toContain("order_by=title_asc");

  // Re-open in list mode for the tag navigation assertion.
  await page.locator('[data-view-mode="list"]').click();
  const chip = page.locator(".gallery-list-row__tags .tag-chip").first();
  await chip.click();
  await expect.poll(() => page.evaluate(() => window.location.hash)).toContain("/library?");
  const hash = await page.evaluate(() => window.location.hash);
  const query = new URLSearchParams(hash.slice(hash.indexOf("?") + 1));
  expect(decodeURIComponent(query.get("tags") ?? "")).toContain(":");
  expect(query.get("tag_mode")).toBe("and");

  expect(csp).toEqual([]);
});

test("single folder fallback heading and empty table keep the layout @polish-favorites", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await mockFavDlBackend(page);

  // An unnamed slot falls back to the localised heading instead of "#N".
  await page.route("**/api/favorites/categories", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          favcat: 1,
          name: "",
          enabled: true,
          mode: "incremental",
          poll_interval_minutes: 720,
          cloud_count: 64,
          local_count: 41,
          cloud_size: 8_200_000_000,
          local_size: 4_100_000_000,
        },
      ]),
    });
  });
  await page.route(/\/api\/favorites\/1\/items/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ total: 0, page: 1, page_size: 24, state: "all", items: [] }),
    });
  });

  await openFolder(page, "/favorites/1");
  const header = page.getByTestId("favlist-header");
  await expect(header.locator("h1")).toHaveText("收藏夹 1");
  await expect(header.locator("h1")).not.toContainText("#1");
  await expectNoGlyphIcons(page, { selector: "[data-testid='favlist-view']" });
  await expect(page.getByTestId("favlist-empty")).toBeVisible();

  // C18: the empty table view still shows its header.
  await page.locator('[data-view-mode="table"]').click();
  await expect(page.getByTestId("favlist-grid-table")).toBeVisible();
  await expect(page.locator(".gallery-table__head")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  expect(csp).toEqual([]);
});

test("polish screenshots for the favourites pages @polish-favorites", async ({ page }) => {
  test.setTimeout(180_000);
  const csp = watchCsp(page);
  await mockFavDlBackend(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(harnessUrl({ view: "favorites" }));

  const directory = await shotMatrix(page, "favorites-directory", {
    url: harnessUrl({ view: "favorites" }),
  });
  expect(directory.files).toHaveLength(4);

  for (const mode of ["grid", "list", "table"] as const) {
    await page.addInitScript((value) => {
      try {
        localStorage.setItem("gv_view_mode", JSON.stringify({ favlist: value }));
      } catch {
        /* storage may be unavailable */
      }
    }, mode);
    const url = harnessUrl({ view: "favlist", path: "/favorites/1" });
    await page.goto(url);
    const shots = await shotMatrix(page, `favlist-${mode}`, { url });
    expect(shots.files).toHaveLength(4);
  }

  expect(csp).toEqual([]);
});
