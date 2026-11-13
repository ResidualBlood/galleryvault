import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import { installLibraryMock, type LibraryMockState } from "./fixtures/library/seed";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
  watchCsp,
} from "./support/polish";

/**
 * po-library polish gate (audit defects LB-01 … LB-14).
 *
 *   - LB-01 / LB-02 page skeleton: header → one-line toolbar → chips → content;
 *     at 390 nothing but the collapsed toolbar stands between the top bar and
 *     the first cover (first card top < 50% of the viewport height).
 *   - LB-03 / LB-04 / LB-06 / LB-14 one control-ladder step per row: toolbar
 *     and panel controls are all 40px and share a centre line.
 *   - LB-05 / LB-13 batch actions moved into the SelectionBar, which only
 *     exists while something is selected.
 *   - LB-07 / LB-08 / LB-09 / LB-10 / LB-11 / LB-12 come from the polished
 *     GalleryCard: independent corners, actions outside the title, tag overlay
 *     on hover, 4 + N tags in list rows.
 *   - view switch (grid / list / table) is per page and survives a reload;
 *     the table sorts on the server; every list request carries tags_limit=0.
 *   - tag clicks append `tags=ns:name` + `tag_mode=and`, chips remove them.
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});


async function openLibrary(
  page: Page,
  options: { total?: number; mode?: "grid" | "list" | "table"; url?: string } = {},
): Promise<LibraryMockState> {
  const state = await installLibraryMock(page, { total: options.total ?? 24 });
  await page.goto(options.url ?? "/#/library");
  await expect(page.getByTestId("library-view")).toBeVisible();
  await expect(page.getByTestId("library-grid")).toBeVisible({ timeout: 20_000 });
  if (options.mode) {
    await page.evaluate(
      (mode) => localStorage.setItem("gv_view_mode", JSON.stringify({ library: mode })),
      options.mode,
    );
    await page.reload();
    await expect(page.getByTestId("library-grid")).toBeVisible({ timeout: 20_000 });
  }
  return state;
}

async function firstCardTop(page: Page): Promise<number> {
  const box = await page.getByTestId("gallery-card").first().boundingBox();
  expect(box).toBeTruthy();
  return Math.round(box!.y);
}

async function rowTops(page: Page, selector: string): Promise<number[]> {
  return page.evaluate((sel) => {
    const row = document.querySelector(sel);
    if (!row) return [];
    return [...row.querySelectorAll("button, input, select")]
      .filter((node) => {
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return rect.width > 1 && rect.height > 1 && style.visibility !== "hidden";
      })
      .map((node) => Math.round(node.getBoundingClientRect().top * 10) / 10);
  }, selector);
}

test("@polish-library toolbar and panel use one control step and aligned rows", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await openLibrary(page, { total: 24 });

  await expectNoGlyphIcons(page, { selector: "[data-testid='library-view']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='library-toolbar']" });

  const toolbar = page.getByTestId("library-toolbar");
  await expectControlHeights(toolbar.locator("button, input"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='library-toolbar']",
    requireRows: true,
    tolerance: 1,
  });

  // LB-03: every toolbar control shares one row (top edges within 1px).
  const tops = await rowTops(page, "[data-testid='library-toolbar']");
  expect(tops.length).toBeGreaterThanOrEqual(4);
  expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(1);

  // LB-02: the first cover is inside the first 1280x900 viewport.
  expect(await firstCardTop(page)).toBeLessThan(450);

  // LB-04 / LB-06 / LB-14: the panel is one grid of equal 40px controls.
  await page.getByTestId("advanced-toggle").click();
  const panel = page.getByTestId("advanced-filters");
  await expect(panel).toBeVisible();
  await expectControlHeights(panel.locator("button, input, select"), 40);
  const panelTops = await rowTops(page, "[data-testid='advanced-filters']");
  expect(panelTops.length).toBeGreaterThan(6);
  await expect(page.getByTestId("filtered-delete")).toBeVisible();

  // LB-01: 390 shows a cover in the first screen, with the panel collapsed.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("library-grid")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("library-filter-sheet")).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
  expect(await firstCardTop(page)).toBeLessThan(422);

  expect(csp).toEqual([]);
});

test("@polish-library filter button badge equals the active condition count", async ({
  page,
}) => {
  await openLibrary(page, { total: 12 });
  await page.getByTestId("advanced-toggle").click();
  const panel = page.getByTestId("advanced-filters");
  await expect(panel).toBeVisible();

  await expect(page.getByTestId("gv-filter-badge")).toHaveCount(0);

  await panel.getByTestId("category-filter").locator("select").selectOption("manga");
  await expect(page.getByTestId("active-filter-chip")).toHaveCount(1);
  await expect(page.getByTestId("gv-filter-badge")).toHaveText("1");
  await expect(page).toHaveURL(/category=manga/);

  await panel.getByTestId("page-min").locator("input").fill("20");
  await panel.getByTestId("page-min").locator("input").blur();
  await expect(page.getByTestId("active-filter-chip")).toHaveCount(2);
  await expect(page.getByTestId("gv-filter-badge")).toHaveText("2");
  await expect(page).toHaveURL(/page_min=20/);

  // Removing one chip drops the condition from the URL and the count.
  await page.getByTestId("active-filter-chip").first().click();
  await expect(page.getByTestId("active-filter-chip")).toHaveCount(1);
  await expect(page.getByTestId("gv-filter-badge")).toHaveText("1");
  await expect(page).not.toHaveURL(/category=manga/);
});

test("@polish-library view mode is per page, survives reload and falls back at 390", async ({
  page,
}) => {
  const state = await openLibrary(page, { total: 24 });
  const toggle = page.getByTestId("view-mode-toggle");
  await expect(toggle.locator('[data-view-mode="grid"]')).toHaveAttribute("aria-pressed", "true");

  await toggle.locator('[data-view-mode="list"]').click();
  await expect(page.getByTestId("gallery-list-row").first()).toBeVisible();
  await expect(page.getByTestId("library-grid")).toHaveAttribute("data-variant", "list");

  await toggle.locator('[data-view-mode="table"]').click();
  const tableRow = page.getByTestId("gallery-table-row").first();
  await expect(tableRow).toBeVisible();
  await expect(page.getByTestId("library-grid")).toHaveAttribute("data-variant", "table");
  // LB-12: table rows keep 3 tags + N even with the selection / action columns.
  expect(await tableRow.locator(".tag-list .tag-chip").count()).toBeLessThanOrEqual(3);
  await expect(tableRow.getByTestId("tag-more")).toHaveText("+2");

  await page.reload();
  await expect(page.getByTestId("gallery-table-row").first()).toBeVisible({ timeout: 20_000 });

  // Every list request asks for the full tag list (be-list-tags).
  expect(state.requests.length).toBeGreaterThan(0);
  for (const request of state.requests) {
    expect(request.get("tags_limit")).toBe("0");
  }

  // 390 cannot render a table: it falls back to list without overwriting the
  // stored preference.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("gallery-list-row").first()).toBeVisible({ timeout: 20_000 });
  await expect(toggle.locator('[data-view-mode="table"]')).toHaveCount(0);
  expect(
    await page.evaluate(() => JSON.parse(localStorage.getItem("gv_view_mode") ?? "{}").library),
  ).toBe("table");

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.reload();
  await expect(page.getByTestId("gallery-table-row").first()).toBeVisible({ timeout: 20_000 });
});

test("@polish-library list tags are translated, clickable and cap at 4 + N", async ({
  page,
}) => {
  const state = await openLibrary(page, { total: 12, mode: "list" });
  const row = page.getByTestId("gallery-list-row").first();
  await expect(row).toBeVisible();

  // LB-12: tags are inline in list rows, capped at 4 with a +N chip.
  const chips = row.locator(".tag-list .tag-chip");
  expect(await chips.count()).toBe(4);
  await expect(row.getByTestId("tag-more")).toHaveText("+1");

  const firstChip = chips.first();
  const zhText = (await firstChip.innerText()).trim();
  expect(zhText.length).toBeGreaterThan(0);

  await firstChip.click();
  await expect(page).toHaveURL(/#\/library\?/);
  const url = new URL(page.url());
  expect(url.hash).toContain("tags=female");
  expect(url.hash).toContain("tag_mode=and");
  await expect(page.getByTestId("active-filter-chip")).toHaveCount(1);
  await expect(page.getByTestId("gv-filter-badge")).toHaveText("1");

  // Second tag click appends instead of replacing (AND).
  const secondRow = page.getByTestId("gallery-list-row").first();
  await expect(secondRow).toBeVisible({ timeout: 20_000 });
  const secondChip = secondRow.locator(".tag-list .tag-chip").nth(1);
  await secondChip.click();
  await expect(page.getByTestId("active-filter-chip")).toHaveCount(2);
  await expect(page.getByTestId("gv-filter-badge")).toHaveText("2");
  const last = state.requests.at(-1);
  expect(last?.get("tags")).toContain("female:");
  expect(last?.get("tags")).toContain("male:");
  expect(last?.get("tag_mode")).toBe("and");

  // Language switch re-renders the chip from `display` without a new request.
  const before = state.requests.length;
  const chip = page.getByTestId("active-filter-chip").first();
  const beforeText = (await chip.innerText()).trim();
  await page.getByTestId("lang-toggle").click();
  const afterText = (await page.getByTestId("active-filter-chip").first().innerText()).trim();
  expect(afterText).not.toBe(beforeText);
  expect(state.requests.length).toBe(before);

  // Removing the first tag chip drops that condition from the next request.
  await page.getByTestId("active-filter-chip").first().click();
  await expect(page.getByTestId("active-filter-chip")).toHaveCount(1);
  await expect
    .poll(() => state.requests.at(-1)?.get("tags") ?? "", { timeout: 10_000 })
    .not.toContain("female:");
});

test("@polish-library grid tags stay in a hover overlay (LB-12)", async ({ page }) => {
  await openLibrary(page, { total: 12 });
  const card = page.getByTestId("gallery-card").first();
  await expect(card).toBeVisible();
  await expect(card.getByTestId("tag-list")).toHaveCount(0);

  await card.hover();
  const overlay = card.getByTestId("card-tag-overlay");
  await expect(overlay).toBeVisible();
  expect(await overlay.locator(".tag-chip").count()).toBeGreaterThan(0);
});

test("@polish-library card corners never overlap and actions stay off the title", async ({
  page,
}) => {
  await openLibrary(page, { total: 12 });

  // LB-07 / LB-10: the selection checkbox and the page badge use different
  // corners; no two corner boxes intersect.
  await page.getByTestId("library-card").first().hover();
  const corners = await page
    .getByTestId("gallery-card")
    .first()
    .locator("[data-corner]")
    .evaluateAll((nodes) =>
      nodes
        .map((node) => {
          const rect = node.getBoundingClientRect();
          return {
            name: node.getAttribute("data-corner") ?? "",
            x: rect.x,
            y: rect.y,
            w: rect.width,
            h: rect.height,
          };
        })
        .filter((box) => box.w > 0 && box.h > 0),
    );
  expect(corners.length).toBeGreaterThanOrEqual(3);
  for (let i = 0; i < corners.length; i += 1) {
    for (let j = i + 1; j < corners.length; j += 1) {
      const a = corners[i];
      const b = corners[j];
      const overlapX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const overlapY = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      expect(
        overlapX > 1 && overlapY > 1,
        `corners ${a.name} and ${b.name} overlap (${overlapX}x${overlapY})`,
      ).toBe(false);
    }
  }

  // LB-08: 390 card actions sit above the title instead of over it.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("library-grid")).toBeVisible({ timeout: 20_000 });
  await expectNoHorizontalOverflow(page);
  const card = page.getByTestId("gallery-card").first();
  const title = card.locator(".gallery-card__title");
  const actions = card.locator(".gallery-card__actions");
  if ((await actions.count()) > 0) {
    const titleBox = await title.boundingBox();
    const actionBox = await actions.boundingBox();
    expect(titleBox && actionBox).toBeTruthy();
    expect(actionBox!.y + actionBox!.height).toBeLessThanOrEqual(titleBox!.y + 1);
  }
  await expect(title).toBeVisible();
});

test("@polish-library selection bar only exists while something is selected", async ({
  page,
}) => {
  await openLibrary(page, { total: 12 });

  await expect(page.getByTestId("gv-selection-bar")).toHaveCount(0);

  const cards = page.getByTestId("library-card");
  await cards.nth(0).locator('input[type="checkbox"]').check();
  await expect(page.getByTestId("gv-selection-bar")).toBeVisible();
  await expect(page.getByTestId("gv-selection-bar")).toContainText("1");
  await expect(page.getByTestId("batch-favorite")).toBeVisible();
  await expect(page.getByTestId("add-to-list")).toBeVisible();
  await expect(page.getByTestId("batch-delete")).toBeVisible();

  await cards.nth(1).locator('input[type="checkbox"]').check();
  await expect(page.getByTestId("gv-selection-bar")).toContainText("2");
  await page.screenshot({ path: join(SHOTS, "library-selection-dark-1280.png") });

  await page.getByTestId("gv-selection-clear").click();
  await expect(page.getByTestId("gv-selection-bar")).toHaveCount(0);
});

test("@polish-library table header sorting maps to order_by", async ({ page }) => {
  const state = await openLibrary(page, { total: 24, mode: "table" });
  const header = page.locator('[data-column="size"]');
  await expect(header).toHaveAttribute("aria-sort", "none");
  await header.locator("button").click();
  await expect(header).toHaveAttribute("aria-sort", "descending");
  await expect
    .poll(() => state.requests.at(-1)?.get("order_by"), { timeout: 10_000 })
    .toBe("file_size_desc");
  // The URL keeps the sort so a reload restores it.
  await expect(page).toHaveURL(/order_by=file_size_desc/);
});

test("@polish-library empty result keeps the table header and an exit", async ({ page }) => {
  await installLibraryMock(page, { total: 0 });
  await page.addInitScript(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ library: "table" })),
  );
  await page.goto("/#/library?page_min=10");
  await expect(page.getByTestId("library-empty")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('[data-column="title"]')).toBeVisible();
  await expect(page.getByTestId("advanced-filters")).toBeVisible();
  await page.getByTestId("library-clear-filters").click();
  await expect(page.getByTestId("active-filter-chip")).toHaveCount(0);
});

test("@polish-library four-variant screenshots", async ({ page }) => {
  await openLibrary(page, { total: 24 });
  await shotMatrix(page, "library-grid", { fullPage: false });

  const panelUrl = new URL(page.url());
  panelUrl.hash = "#/library?page_min=1";
  await page.goto(panelUrl.toString());
  await expect(page.getByTestId("advanced-filters")).toBeVisible({ timeout: 20_000 });
  await shotMatrix(page, "library-panel", { url: page.url(), fullPage: false });

  await page.goto("/#/library");
  await page.evaluate(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ library: "list" })),
  );
  await page.reload();
  await expect(page.getByTestId("gallery-list-row").first()).toBeVisible({ timeout: 20_000 });
  await shotMatrix(page, "library-list", { fullPage: false });

  await page.evaluate(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ library: "table" })),
  );
  await page.reload();
  await expect(page.getByTestId("gallery-table-row").first()).toBeVisible({ timeout: 20_000 });
  await shotMatrix(page, "library-table", { fullPage: false });
});
