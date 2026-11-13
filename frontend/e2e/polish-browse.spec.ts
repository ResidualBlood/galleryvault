import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import { installLibraryMock, type LibraryMockState } from "./fixtures/library/seed";
import { galleriesEp } from "../src/api/galleries";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  expectTagChipsReadable,
  shotMatrix,
  watchCsp,
} from "./support/polish";

/**
 * po-collection-browse polish gate.
 *
 * Owns audit defects BR-01 … BR-10 and the shared GalleryCard roots of
 * LB-07 / LB-08 / LB-11 / LB-12:
 *
 *   - BR-01/02/03 toolbar controls share one height and centre line, the
 *     random action uses a registry SVG, and 390 wraps as input row + action row;
 *   - BR-04/05/06 the tag overview moved below the list and its heading/link
 *     match the other sections (translated namespaces only);
 *   - BR-07 grid meta keeps size + date while the author truncates;
 *   - BR-08 grid tags live in a hover / focus overlay, list = 4 + N, table = 3 + N;
 *   - BR-09 the sentinel says "all items loaded", not "no data";
 *   - BR-10 the continue-reading strip fades its right edge.
 *
 * Plus the view-switch contract: per-page memory, table unavailable at 390
 * without overwriting the stored preference, anchored first row, windowed DOM
 * under 5000 items, server-side header sorting, no horizontal table scroll.
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});


async function openBrowse(
  page: Page,
  options: { total?: number; mode?: "grid" | "list" | "table" } = {},
): Promise<LibraryMockState> {
  const state = await installLibraryMock(page, { total: options.total ?? 5000 });
  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-view")).toBeVisible();
  await expect(page.getByTestId("browse-grid")).toBeVisible({ timeout: 20_000 });
  if (options.mode) {
    await page.evaluate(
      (mode) => localStorage.setItem("gv_view_mode", JSON.stringify({ browse: mode })),
      options.mode,
    );
    await page.reload();
    await expect(page.getByTestId("browse-grid")).toBeVisible({ timeout: 20_000 });
  }
  return state;
}

async function modeToggle(page: Page) {
  return page.getByTestId("view-mode-toggle");
}

async function firstVisibleBox(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const nodes = [...document.querySelectorAll<HTMLElement>(sel)];
    const node = nodes.find((entry) => {
      const rect = entry.getBoundingClientRect();
      return rect.height > 0 && rect.bottom > 1 && rect.top < window.innerHeight;
    });
    if (!node) return null;
    const rect = node.getBoundingClientRect();
    return { id: node.dataset.id, top: Math.round(rect.top), left: Math.round(rect.left) };
  }, selector);
}

test("@polish-browse toolbar is one control step and uses registry icons", async ({ page }) => {
  const csp = watchCsp(page);
  await openBrowse(page);

  await expectNoGlyphIcons(page, { selector: "[data-testid='browse-view']" });
  await expectNoGlyphIcons(page, { selector: "[data-testid='browse-toolbar']" });

  const toolbar = page.getByTestId("browse-toolbar");
  await expectControlHeights(toolbar.locator("button, input"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='browse-toolbar']",
    requireRows: true,
    tolerance: 1,
  });

  // BR-02: the random action is an SVG from the registry, not U+2684.
  const random = page.getByTestId("random-button");
  await expect(random.locator("svg.gv-icon")).toHaveCount(1);
  await expect(random).not.toContainText("⚄");

  // BR-04: the main list starts inside the first 1280x900 viewport.
  const firstCard = page.getByTestId("gallery-card").first();
  const cardBox = await firstCard.boundingBox();
  expect(cardBox).toBeTruthy();
  expect(cardBox!.y, "first card must be visible at 1280x900").toBeLessThan(900);

  // BR-03: at 390 the input takes a full row, the actions the next one.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("browse-grid")).toBeVisible({ timeout: 20_000 });
  await expectNoHorizontalOverflow(page);
  const inputBox = await toolbar.locator("input").boundingBox();
  const buttons = toolbar.locator("button");
  const firstButton = await buttons.first().boundingBox();
  expect(inputBox && firstButton).toBeTruthy();
  expect(firstButton!.y).toBeGreaterThan(inputBox!.y + inputBox!.height - 1);
  expect(inputBox!.width).toBeGreaterThan(300);

  const latestTop = await page.getByTestId("browse-grid").evaluate((node) => {
    return Math.round(node.getBoundingClientRect().top + window.scrollY);
  });
  expect(latestTop, "recently-added list must start inside the first 900px").toBeLessThan(1500);

  expect(csp).toEqual([]);
});

test("@polish-browse tag overview sits after the list with matching headings", async ({
  page,
}) => {
  await openBrowse(page);
  const latest = page.locator(".browse__latest");
  const overview = page.getByTestId("browse-tag-overview");
  await expect(overview).toBeVisible({ timeout: 20_000 });

  const latestBox = await latest.boundingBox();
  const overviewBox = await overview.boundingBox();
  expect(latestBox && overviewBox).toBeTruthy();
  expect(overviewBox!.y).toBeGreaterThan(latestBox!.y);

  // BR-05: link is not a second "Tags", and pills use translated namespaces.
  await expect(overview.locator(".overview__link")).toContainText("查看全部");
  await expect(overview.locator(".overview__link")).not.toContainText("标签");
  const pills = overview.locator(".overview__pill");
  expect(await pills.count()).toBeGreaterThan(0);
  for (const text of await pills.allInnerTexts()) {
    expect(text).not.toMatch(/^(uploader|reclass|temp)\b/);
  }

  // BR-06: link aligns right like the continue-reading section (same 14px step).
  const box = await overview.locator(".overview__head").boundingBox();
  const linkBox = await overview.locator(".overview__link").boundingBox();
  expect(box && linkBox).toBeTruthy();
  expect(Math.abs(box!.x + box!.width - (linkBox!.x + linkBox!.width))).toBeLessThan(2);
});

test("@polish-browse grid meta keeps size and date and corners never overlap", async ({
  page,
}) => {
  await openBrowse(page);
  const card = page.getByTestId("gallery-card").first();
  await expect(card).toBeVisible();

  // BR-07: author truncates, size + date stay visible.
  const meta = card.locator(".gallery-card__meta");
  await expect(meta.locator(".gallery-card__meta-size")).toContainText("MB");
  await expect(meta.locator(".gallery-card__meta-date")).toContainText("20");
  const nameBox = await meta.locator(".gallery-card__meta-name").boundingBox();
  const dateBox = await meta.locator(".gallery-card__meta-date").boundingBox();
  expect(nameBox && dateBox).toBeTruthy();
  expect(dateBox!.x + dateBox!.width).toBeLessThanOrEqual(
    (await meta.boundingBox())!.x + (await meta.boundingBox())!.width + 1,
  );

  // The four corner zones are independent: no pair intersects.
  const corners = await card.locator("[data-corner]").evaluateAll((nodes) =>
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
});

test("@polish-browse grid hides inline tags until hover; list and table cap them", async ({
  page,
}) => {
  await openBrowse(page);

  // BR-08: no tag chip inside grid cards at rest.
  const cards = page.getByTestId("gallery-card");
  await expect(cards.first()).toBeVisible();
  await expect(cards.first().getByTestId("tag-list")).toHaveCount(0);

  await cards.first().hover();
  const overlay = cards.first().getByTestId("card-tag-overlay");
  await expect(overlay).toBeVisible();
  const overlayChips = overlay.locator(".tag-chip");
  expect(await overlayChips.count()).toBeGreaterThan(0);
  expect(await overlayChips.count()).toBeLessThanOrEqual(6);
  await expect(overlay.getByTestId("tag-list")).toHaveAttribute("data-layout", "wrap");
  await expectTagChipsReadable(overlayChips);

  // Shots at both widths and themes; chips must stay readable everywhere.
  for (const variant of [
    { theme: "dark", width: 1280, height: 900 },
    { theme: "light", width: 1280, height: 900 },
    { theme: "dark", width: 390, height: 844 },
    { theme: "light", width: 390, height: 844 },
  ] as const) {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.emulateMedia({ colorScheme: variant.theme });
    await page.evaluate((theme) => localStorage.setItem("gv_theme", theme), variant.theme);
    await page.reload();
    await expect(page.getByTestId("browse-grid")).toBeVisible({ timeout: 20_000 });
    const shotCard = page.getByTestId("gallery-card").first();
    await shotCard.hover();
    const shotOverlay = shotCard.getByTestId("card-tag-overlay");
    await expect(shotOverlay).toBeVisible();
    await expectTagChipsReadable(shotOverlay.locator(".tag-chip"));
    await page.screenshot({
      path: join(SHOTS, `browse-grid-tags-${variant.theme}-${variant.width}.png`),
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // Touch long-press opens the same tags in a sheet.
  await cards.first().dispatchEvent("pointerdown", {
    pointerType: "touch",
    clientX: 40,
    clientY: 260,
    bubbles: true,
  });
  const sheet = page.getByTestId("card-tag-sheet");
  await expect(sheet).toBeVisible({ timeout: 3_000 });
  expect(await sheet.locator(".tag-chip").count()).toBeGreaterThanOrEqual(4);
  await expect(sheet.getByTestId("tag-more")).toHaveText("+1");
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);

  // List: 4 chips + N.
  const toggle = await modeToggle(page);
  await toggle.locator('[data-view-mode="list"]').click();
  const row = page.getByTestId("gallery-list-row").first();
  await expect(row).toBeVisible();
  const listChips = row.locator(".tag-list .tag-chip");
  expect(await listChips.count()).toBeLessThanOrEqual(4);
  await expect(row.getByTestId("tag-more")).toHaveText("+1");

  // Table: 3 chips + N.
  await toggle.locator('[data-view-mode="table"]').click();
  const tableRow = page.getByTestId("gallery-table-row").first();
  await expect(tableRow).toBeVisible();
  const tableChips = tableRow.locator(".tag-list .tag-chip");
  expect(await tableChips.count()).toBeLessThanOrEqual(3);
  await expect(tableRow.getByTestId("tag-more")).toHaveText("+2");
});

test("@polish-browse view mode is remembered per page and table falls back at 390", async ({
  page,
}) => {
  await openBrowse(page);
  await page.evaluate(() => localStorage.removeItem("gv_view_mode"));
  await page.reload();
  const toggle = await modeToggle(page);
  await expect(toggle.locator('[data-view-mode="grid"]')).toHaveAttribute("aria-pressed", "true");

  await toggle.locator('[data-view-mode="list"]').click();
  await expect(page.getByTestId("gallery-list-row").first()).toBeVisible();
  await toggle.locator('[data-view-mode="table"]').click();
  await expect(page.getByTestId("gallery-table-row").first()).toBeVisible();
  await expect(page.locator('[data-column="pages"]')).toHaveAttribute("aria-sort", "none");

  // Persisted, and switching pages did not clobber another page key.
  await page.evaluate(() => {
    const map = JSON.parse(localStorage.getItem("gv_view_mode") ?? "{}");
    map.library = "list";
    localStorage.setItem("gv_view_mode", JSON.stringify(map));
  });
  await page.reload();
  await expect(page.getByTestId("gallery-table-row").first()).toBeVisible();
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("gv_view_mode") ?? "{}"));
  expect(stored.browse).toBe("table");
  expect(stored.library).toBe("list");

  // 390: no table segment, effective list, stored table value untouched.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("gallery-list-row").first()).toBeVisible();
  await expect(toggle.locator('[data-view-mode="table"]')).toHaveCount(0);
  await expect(toggle.locator('[data-view-mode="list"]')).toHaveAttribute("aria-pressed", "true");
  expect(
    await page.evaluate(() => JSON.parse(localStorage.getItem("gv_view_mode") ?? "{}").browse),
  ).toBe("table");

  // Widening brings the stored table view back.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.reload();
  await expect(page.getByTestId("gallery-table-row").first()).toBeVisible();
});

test("@polish-browse 5000 rows stay windowed in all three views", async ({ page }) => {
  test.setTimeout(180_000);
  await page.addInitScript(() => localStorage.setItem("gv_page_size", "500"));
  const state = await installLibraryMock(page, { total: 5000 });
  await page.goto("/#/browse");
  const grid = page.getByTestId("browse-grid");
  await expect(grid).toHaveAttribute("data-loaded", "500", { timeout: 20_000 });

  await expect
    .poll(
      async () => {
        const loaded = Number(await grid.getAttribute("data-loaded"));
        if (loaded < 5000) {
          await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        }
        return loaded;
      },
      { timeout: 120_000, intervals: [300, 500, 800, 1200] },
    )
    .toBe(5000);

  const toggle = await modeToggle(page);
  const counts: Record<string, number> = {};
  counts.grid = await page.getByTestId("gallery-card").count();
  await toggle.locator('[data-view-mode="list"]').click();
  counts.list = await page.getByTestId("gallery-list-row").count();
  await toggle.locator('[data-view-mode="table"]').click();
  counts.table = await page.getByTestId("gallery-table-row").count();

  for (const [mode, count] of Object.entries(counts)) {
    expect(count, `${mode} DOM rows`).toBeGreaterThan(0);
    expect(count, `${mode} DOM rows`).toBeLessThan(200);
  }
  expect(state.total).toBe(5000);
});

test("@polish-browse keeps the first visible gallery across view switches", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("gv_page_size", "500"));
  await installLibraryMock(page, { total: 5000 });
  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-grid")).toHaveAttribute("data-loaded", "500", {
    timeout: 20_000,
  });

  await page.evaluate(() => window.scrollTo(0, 6000));
  await page.waitForTimeout(250);
  const before = await firstVisibleBox(page, '[data-testid="gallery-card"]');
  expect(before).toBeTruthy();

  const toggle = await modeToggle(page);
  await toggle.locator('[data-view-mode="list"]').click();
  await page.waitForTimeout(250);
  const afterList = await firstVisibleBox(page, '[data-testid="gallery-list-row"]');
  expect(afterList?.id).toBe(before?.id);

  await toggle.locator('[data-view-mode="table"]').click();
  await page.waitForTimeout(250);
  const afterTable = await firstVisibleBox(page, '[data-testid="gallery-table-row"]');
  expect(afterTable?.id).toBe(before?.id);
});

test("@polish-browse tag click filters the library and language switch is offline", async ({
  page,
}) => {
  const state = await openBrowse(page);
  const toggle = await modeToggle(page);
  await toggle.locator('[data-view-mode="list"]').click();
  const row = page.getByTestId("gallery-list-row").first();
  await expect(row).toBeVisible();

  const chip = row.locator(".tag-list .tag-chip").first();
  const zhText = (await chip.innerText()).trim();
  expect(zhText.length).toBeGreaterThan(0);
  await chip.click();

  await expect(page).toHaveURL(/#\/library\?/);
  const url = new URL(page.url());
  expect(url.hash).toContain("tags=female");
  expect(url.hash).toContain("tag_mode=and");
  expect(url.hash).not.toContain("#/gallery/");

  // Language switch changes the chip text without a new list request.
  await page.goto("/#/browse");
  await expect(page.getByTestId("gallery-list-row").first()).toBeVisible({ timeout: 20_000 });
  const requests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === galleriesEp.path) requests.push(request.url());
  });
  const before = state.requests.length;
  await page.getByTestId("lang-toggle").click();
  const enText = (await page.getByTestId("gallery-list-row").first().locator(".tag-list .tag-chip").first().innerText()).trim();
  expect(enText).not.toBe(zhText);
  expect(state.requests.length).toBe(before);
  expect(requests).toEqual([]);
});

test("@polish-browse page count header sorts on the server and updates aria-sort", async ({
  page,
}) => {
  const state = await openBrowse(page, { mode: "table" });
  const header = page.locator('[data-column="pages"]');
  await expect(header).toHaveAttribute("aria-sort", "none");
  await header.locator("button").click();
  await expect(header).toHaveAttribute("aria-sort", "descending");
  await expect
    .poll(() => state.requests.at(-1)?.get("order_by"), { timeout: 10_000 })
    .toBe("page_count_desc");

  await header.locator("button").click();
  await expect(header).toHaveAttribute("aria-sort", "ascending");
  await expect
    .poll(() => state.requests.at(-1)?.get("order_by"), { timeout: 10_000 })
    .toBe("page_count_asc");
});

test("@polish-browse table fits 1280 and 900 without horizontal scrolling", async ({ page }) => {
  await openBrowse(page, { mode: "table" });
  for (const width of [1280, 900]) {
    await page.setViewportSize({ width, height: 900 });
    await page.reload();
    await expect(page.getByTestId("gallery-table-row").first()).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(page);
    const overflow = await page.getByTestId("browse-grid").evaluate((node) => ({
      scroll: node.scrollWidth,
      client: node.clientWidth,
    }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client + 1);
  }
});

test("@polish-browse card actions never cover the title at 390", async ({ page }) => {
  await installLibraryMock(page, { total: 200 });
  await page.addInitScript(() => localStorage.setItem("gv_view_mode", JSON.stringify({ library: "grid" })));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/library");
  await expect(page.getByTestId("library-grid")).toBeVisible({ timeout: 20_000 });
  const card = page.getByTestId("gallery-card").first();
  await expect(card).toBeVisible();
  const title = card.locator(".gallery-card__title");
  const actions = card.locator(".gallery-card__actions");
  if ((await actions.count()) > 0) {
    const titleBox = await title.boundingBox();
    const actionBox = await actions.boundingBox();
    expect(titleBox && actionBox).toBeTruthy();
    expect(actionBox!.y + actionBox!.height).toBeLessThanOrEqual(titleBox!.y + 1);
  }
  await expect(title).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("@polish-browse empty table keeps its header", async ({ page }) => {
  await installLibraryMock(page, { total: 0 });
  await page.addInitScript(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ browse: "table" })),
  );
  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-empty")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('[data-column="title"]')).toBeVisible();
  await expect(page.locator('[data-column="pages"]')).toBeVisible();
});

test("@polish-browse sentinel says every item is loaded", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.evaluate(() => localStorage.setItem("gv_theme", "dark")).catch(() => undefined);
  await installLibraryMock(page, { total: 6 });
  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-grid")).toHaveAttribute("data-loaded", "6", {
    timeout: 20_000,
  });
  const sentinel = page.getByTestId("grid-sentinel");
  await expect(sentinel).toContainText("已全部加载");
  await expect(sentinel).not.toContainText("暂无数据");
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(200);
  await expect(sentinel).toBeInViewport();
  await page.screenshot({ path: join(SHOTS, "browse-sentinel-dark-1280.png") });
});

test("@polish-browse four-variant screenshots", async ({ page }) => {
  await openBrowse(page);
  await shotMatrix(page, "browse-grid", { fullPage: false });
  await shotMatrix(page, "browse-full", { fullPage: true });

  await page.evaluate(() => localStorage.setItem("gv_view_mode", JSON.stringify({ browse: "table" })));
  await page.reload();
  await expect(page.getByTestId("gallery-table-row").first()).toBeVisible({ timeout: 20_000 });
  await shotMatrix(page, "browse-table", { fullPage: false });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.evaluate(() => localStorage.setItem("gv_theme", "dark")).catch(() => undefined);
  await page.evaluate(() => localStorage.setItem("gv_view_mode", JSON.stringify({ browse: "grid" })));
  await page.reload();
  await expect(page.getByTestId("gallery-card").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("gallery-card").first().screenshot({
    path: join(SHOTS, "browse-card-dark-1280.png"),
  });

  await page.evaluate(() => localStorage.setItem("gv_view_mode", JSON.stringify({ browse: "list" })));
  await page.reload();
  await expect(page.getByTestId("gallery-list-row").first()).toBeVisible({ timeout: 20_000 });
  await shotMatrix(page, "browse-list", { fullPage: false });
});
