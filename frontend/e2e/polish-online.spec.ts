import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import { mockOnlineBackend } from "./fixtures/online/mock";
import { ehSearchEp } from "../src/api/eh";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

/**
 * po-online-list polish gate (audit OL-01 … OL-13).
 *
 * The list is the default view: every row carries category, pages, rating,
 * uploader, posted time and the inferred language, plus at most four tag chips
 * and `+N`. Tag clicks append an exact `ns:"name$"` query to the search box and
 * never issue a second EH request; grid / table reuse the shared collection
 * components through the same append contract.
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

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

async function openOnline(
  page: Page,
  options: { mode?: "grid" | "list" | "table"; stored?: Record<string, string> } = {},
): Promise<void> {
  await page.addInitScript((stored) => {
    if (sessionStorage.getItem("gv_polish_seeded")) return;
    sessionStorage.setItem("gv_polish_seeded", "1");
    localStorage.removeItem("gv_view_mode");
    if (stored) localStorage.setItem("gv_view_mode", JSON.stringify(stored));
  }, options.stored ?? {});
  await mockOnlineBackend(page);
  await page.goto("/#/online");
  await expect(page.getByTestId("online-view")).toBeVisible();
  await expect(page.getByTestId("online-grid")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "12");
  if (options.mode) {
    await page.evaluate(
      (mode) => localStorage.setItem("gv_view_mode", JSON.stringify({ online: mode })),
      options.mode,
    );
    await page.reload();
    await expect(page.getByTestId("online-grid")).toBeVisible({ timeout: 20_000 });
  }
}

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

test("@polish-online toolbar and filter row use one control step", async ({ page }) => {
  const csp = watchCsp(page);
  await openOnline(page);

  // The legacy hidden ♥ marker is gone; only rendered icons remain.
  await expectNoGlyphIcons(page, { selector: "[data-testid='online-view']" });

  const toolbar = page.getByTestId("online-toolbar");
  await expectControlHeights(toolbar.locator("button, input"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='online-toolbar']",
    requireRows: true,
    tolerance: 1,
  });

  // Filter row: the segmented frame, rating/toplist selects and category chips
  // all use the 32px sm step; the segments inside the frame are 4px shorter.
  const filters = page.getByTestId("online-filters-row");
  await expectControlHeights(filters.locator("select, button:not([data-segmented-value])"), 32);
  const listTypes = filters.getByTestId("online-list-types");
  expect((await listTypes.boundingBox())!.height).toBeCloseTo(32, 0);
  const smStep = await page.evaluate(() =>
    Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--gv-size-control-sm"),
    ),
  );
  await expectControlHeights(listTypes.locator("[data-segmented-value]"), smStep - 4);
  await expect(filters.getByTestId("online-min-rating")).toBeVisible();
  await expect(filters.getByTestId("online-cat-all")).toBeVisible();

  // OL-06: exactly one filled primary action on the page, and it is search.
  const filled = page.getByTestId("online-view").locator("button.btn--filled:visible");
  await expect(filled).toHaveCount(1);
  await expect(filled.first()).toHaveText("搜索");

  // OL-11: every icon is a registry SVG, never a Unicode glyph.
  await expect(toolbar.locator("button svg.gv-icon").first()).toBeVisible();
  expect(await page.locator("iframe").count()).toBe(0);
  expect(csp).toEqual([]);
});

test("@polish-online list rows expose category, meta, language and 4+N tags", async ({ page }) => {
  const csp = watchCsp(page);
  await openOnline(page);

  const cards = page.getByTestId("online-card");
  const first = cards.first();
  const row = first.locator(".online-row");
  await expect(row).toBeVisible();

  // OL-01 / OL-13: all six C03 fields are present in one row.
  await expect(row.getByTestId("online-row-category")).toContainText("漫画");
  await expect(row.getByTestId("online-row-pages")).toContainText("11P");
  await expect(row.getByTestId("online-row-rating")).toContainText("3.5");
  const meta = row.getByTestId("online-row-meta");
  await expect(meta).toContainText("fixture-uploader");
  await expect(meta).toContainText("2025-11-01");
  await expect(meta).toContainText("中文");

  // OL-01: 4 visible chips + N (language has its own meta slot and is excluded).
  const chips = row.locator(".tag-list .tag-chip");
  expect(await chips.count()).toBeLessThanOrEqual(4);
  await expect(row.getByTestId("tag-more")).toHaveText("+1");

  // OL-02: no internal blank block taller than 40px.
  const maxGap = await row.evaluate((element) => {
    const blocks = [
      ...element.querySelectorAll<HTMLElement>(
        ".online-row__title, .online-row__sub, .online-row__tags, .online-row__tags-empty, .online-row__bottom",
      ),
    ]
      .map((node) => node.getBoundingClientRect())
      .filter((box) => box.height > 0 && box.width > 0)
      .sort((a, b) => a.top - b.top);
    let gap = 0;
    for (let index = 1; index < blocks.length; index += 1) {
      gap = Math.max(gap, blocks[index].top - blocks[index - 1].bottom);
    }
    return gap;
  });
  expect(maxGap, "the list row must not contain a blank block over 40px").toBeLessThan(40);

  // OL-03: category appears once (bottom line), never on the cover.
  expect(await row.locator("[data-testid='online-row-category']").count()).toBe(1);
  expect(await row.locator(".badge-strip").count()).toBe(1);

  // OL-12: the favourite heart is visible without hovering and is clickable.
  const fav = row.getByTestId("fav-button");
  await expect(fav).toBeVisible();
  expect(await row.getByTestId("download-button").count()).toBeGreaterThan(0);

  // A row without tags keeps the same height and renders an em dash.
  const emptyRow = cards.nth(1).locator(".online-row");
  await expect(emptyRow.getByTestId("online-row-tags-empty")).toBeVisible();
  const heights = await cards.evaluateAll((nodes) =>
    nodes.slice(0, 10).map((node) => Math.round(node.getBoundingClientRect().height)),
  );
  expect(new Set(heights).size, "empty-tag rows keep the regular row height").toBe(1);
  expect(csp).toEqual([]);
});

test("@polish-online tag clicks append an exact query and reload no extra EH request", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await openOnline(page);

  const searches: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === ehSearchEp.path) searches.push(url.searchParams.get("q") ?? "");
  });

  const row = page.getByTestId("online-card").first().locator(".online-row");
  const chip = row.locator(".tag-list .tag-chip").first();
  await expect(chip).toContainText("巨乳");

  const tailored = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return (
      url.pathname === ehSearchEp.path &&
      url.searchParams.get("q") === 'female:"big breasts$"'
    );
  });
  await chip.click();
  await tailored;
  await expect(page.getByTestId("online-search").locator("input")).toHaveValue(
    'female:"big breasts$"',
  );
  await expect(page).toHaveURL(/q=female/);

  // A second tag is appended with a space (AND) instead of replacing the first.
  const second = page.getByTestId("online-card").first().locator(".tag-list .tag-chip").nth(3);
  await second.click();
  await expect(page.getByTestId("online-search").locator("input")).toHaveValue(
    'female:"big breasts$" artist:fixture-artist$',
  );

  // Switching language only re-renders labels; no new search request is made.
  const before = searches.length;
  await expect(page.getByTestId("online-card").first().locator(".tag-list .tag-chip").first()).toContainText(
    "巨乳",
  );
  await page.getByTestId("lang-toggle").click();
  await expect(
    page.getByTestId("online-card").first().locator(".tag-list .tag-chip").first(),
  ).toContainText("big breasts");
  await page.waitForTimeout(250);
  expect(searches.length).toBe(before);
  expect(csp).toEqual([]);
});

test("@polish-online view toggle is per page and 390 keeps the toolbar on two full rows", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await openOnline(page, { stored: { library: "grid" } });

  const grid = page.getByTestId("online-grid");
  const toggle = page.getByTestId("view-mode-toggle");
  await toggle.locator('[data-view-mode="grid"]').click();
  await expect(grid).toHaveAttribute("data-mode", "grid");
  await expect(grid.getByTestId("gallery-card").first()).toBeVisible();

  await toggle.locator('[data-view-mode="table"]').click();
  await expect(grid).toHaveAttribute("data-mode", "table");
  await expect(grid.getByTestId("gallery-table-row").first()).toBeVisible();

  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("gv_view_mode") ?? "{}"));
  expect(stored.online).toBe("table");
  expect(stored.library, "online preference must not leak into the library").toBe("grid");

  // 390: table preference stays stored but the page falls back to list.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(grid).toBeVisible({ timeout: 20_000 });
  await expect(grid).toHaveAttribute("data-mode", "list");
  const compact = await page.evaluate(
    () => JSON.parse(localStorage.getItem("gv_view_mode") ?? "{}"),
  );
  expect(compact.online).toBe("table");

  await expectNoHorizontalOverflow(page);
  const toolbar = page.getByTestId("online-toolbar");
  const boxes = await toolbar.evaluate((element) => {
    const children = [...element.children].map((node) => {
      const rect = node.getBoundingClientRect();
      return { top: Math.round(rect.top), kind: node.tagName.toLowerCase() };
    });
    const groups: Array<{ top: number; count: number; hasInput: boolean }> = [];
    for (const child of children) {
      const group = groups.find((entry) => Math.abs(entry.top - child.top) <= 2);
      if (group) {
        group.count += 1;
        group.hasInput = group.hasInput || child.kind === "label";
      } else {
        groups.push({ top: child.top, count: 1, hasInput: child.kind === "label" });
      }
    }
    return groups;
  });
  for (const group of boxes) {
    if (group.hasInput) continue;
    expect(group.count, "390 toolbar actions must never leave one control alone").toBeGreaterThan(1);
  }
  expect(csp).toEqual([]);
});

test("@polish-online states produce dark/light x 1280/390 screenshots", async ({ page }) => {
  const csp = watchCsp(page);
  await openOnline(page);
  await shotMatrix(page, "online-list", { url: "/#/online" });

  await page.evaluate(
    (mode) => localStorage.setItem("gv_view_mode", JSON.stringify({ online: mode })),
    "grid",
  );
  await shotMatrix(page, "online-grid", { url: "/#/online" });

  await page.evaluate(
    (mode) => localStorage.setItem("gv_view_mode", JSON.stringify({ online: mode })),
    "table",
  );
  await shotMatrix(page, "online-table", { url: "/#/online" });
  expect(csp).toEqual([]);
});
