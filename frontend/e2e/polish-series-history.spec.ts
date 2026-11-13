import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import { installLibManageMock } from "./fixtures/lib-manage/mock";
import { mockFavDlBackend } from "./fixtures/fav-dl/mock";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

/**
 * po-series-history polish gate.
 *
 * Series (SR-01 … SR-09) is a grouped collection: PageHeader → toolbar with
 * grid / list only → selection bar → grouped GalleryCards → footer Pager.
 * History (HS-01 … HS-07) is a list / table / grid collection whose default is
 * the list view; rows carry progress, last-read time and the continue-reading
 * action, while the destructive clear actions keep the danger semantics.
 *
 * Covers the audit's P1s: SR-01 badge never wraps vertically at 390, HS-01 no
 * horizontal overflow at 390 and HS-02 title ellipsis on long titles.
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

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

/** 1x1 PNG so fixture cover URLs never render a broken image in screenshots. */
const PIXEL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

async function installThumbStub(page: Page): Promise<void> {
  await page.route("**/api/galleries/*/thumb/*", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/png", body: PIXEL_PNG });
  });
}

const LONG_TITLE = [
  "【中文标题】This history title is deliberately long enough to be clamped without widening the document",
  "[PTBR] はじめてのおつかい とても長いタイトルがカードの外へはみ出さないことを確認する",
  "A second sentence keeps the row well beyond two lines so the clamp is measurable",
  "第三段落：标题应该在两行处截断，而不是把文档撑到视口之外。",
].join(" ");

function historyEntry(index: number, title = LONG_TITLE) {
  return {
    gallery_id: 1000 + index,
    current_page: 3 + index,
    total_pages: 24 + index,
    last_read_at: new Date(Date.UTC(2025, 9, 20 - index, 12, 30)).toISOString(),
    title,
    display_title: title,
    raw_title: title,
    title_jpn: null,
    gid: 7000 + index,
    category: ["doujinshi", "manga", "artistcg"][index % 3],
    url: `/galleries/${1000 + index}`,
  };
}

async function installHistoryLongTitles(page: Page): Promise<void> {
  await page.route("**/api/history**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 12,
        page: 1,
        page_size: 24,
        items: Array.from({ length: 12 }, (_, index) => historyEntry(index)),
      }),
    });
  });
}

async function openSeries(page: Page): Promise<void> {
  const state = await installLibManageMock(page);
  await installThumbStub(page);
  await page.goto("/#/series");
  await expect(page.getByTestId("series-view")).toBeVisible();
  await expect(page.getByTestId("series-group")).toHaveCount(3);
  expect(state.seriesCreates).toEqual([]);
}

async function openHistory(page: Page): Promise<void> {
  await mockFavDlBackend(page, { totalHistory: 12 });
  await installHistoryLongTitles(page);
  await page.goto("/#/history");
  await expect(page.getByTestId("history-view")).toBeVisible();
  await expect(page.getByTestId("history-list")).toHaveAttribute("data-loaded", "12");
}

test("@polish-series-history series toolbar and group header stay aligned", async ({ page }) => {
  const csp = watchCsp(page);
  await openSeries(page);

  await expectNoGlyphIcons(page, { selector: "[data-testid='series-view']" });

  const toolbar = page.getByTestId("series-toolbar");
  await expectControlHeights(toolbar.locator("button, select, input"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='series-toolbar']",
    requireRows: true,
    tolerance: 1,
  });

  // SR-02 / SR-03: the pager is a footer Pager with SVG chevrons, not text.
  const pager = page.getByTestId("series-pager");
  await expect(pager).toBeVisible();
  await expect(pager.locator('[data-pager="prev"] svg.gv-icon')).toHaveCount(1);
  await expect(pager.locator('[data-pager="next"] svg.gv-icon')).toHaveCount(1);

  // Series has no table view: the toggle offers grid + list only.
  const toggle = page.getByTestId("series-view-toggle");
  await expect(toggle.locator("[data-view-mode]")).toHaveCount(2);
  await expect(toggle.locator('[data-view-mode="table"]')).toHaveCount(0);

  // SR-07: delete is the danger action, separated from the tonal add button.
  await expect(page.getByTestId("series-add-item").first()).toHaveClass(/btn--tonal/);
  await expect(page.getByTestId("series-delete").first()).toHaveClass(/btn--danger/);

  // SR-06: member cards never print raw category keys; they use the label.
  const member = page.getByTestId("series-member").first();
  await expect(member).toContainText("同人志");
  await expect(member).not.toContainText("doujinshi");

  expect(csp).toEqual([]);
});

test("@polish-series-history series grid / list switch is remembered per page", async ({
  page,
}) => {
  await openSeries(page);
  const toggle = page.getByTestId("series-view-toggle");

  await toggle.locator('[data-view-mode="list"]').click();
  await expect(toggle).toHaveAttribute("data-mode", "list");
  await expect(page.locator("[data-testid='series-member'] .gallery-card-list").first()).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("series-view-toggle")).toHaveAttribute("data-mode", "list");

  await page.getByTestId("series-view-toggle").locator('[data-view-mode="grid"]').click();
  await expect(page.getByTestId("series-view-toggle")).toHaveAttribute("data-mode", "grid");
  await expect(page.locator("[data-testid='series-member'] .gallery-card").first()).toBeVisible();
});

test("@polish-series-history series badge keeps its width at 390 without overflow", async ({
  page,
}) => {
  await openSeries(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("series-group").first()).toBeVisible();
  await expectNoHorizontalOverflow(page);

  // SR-01: the auto badge must not collapse into a vertical two-character box.
  const badge = page.getByTestId("series-group-badge").first();
  const box = await badge.boundingBox();
  expect(box).toBeTruthy();
  expect(box!.height).toBeLessThanOrEqual(24);
  expect(box!.width).toBeGreaterThan(box!.height);

  // The group title truncates instead of widening the page.
  const title = page.locator(".group__title").first();
  const titleBox = await title.boundingBox();
  const headBox = await page.locator(".group__head").first().boundingBox();
  expect(titleBox && headBox).toBeTruthy();
  expect(titleBox!.x + titleBox!.width).toBeLessThanOrEqual(headBox!.x + headBox!.width + 1);
});

test("@polish-series-history history list / table / grid switch and long title ellipsis", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await openHistory(page);

  await expectNoGlyphIcons(page, { selector: "[data-testid='history-view']" });

  const toggle = page.getByTestId("history-view-toggle");
  await expect(toggle).toHaveAttribute("data-mode", "list");
  await expect(toggle.locator("[data-view-mode]")).toHaveCount(3);

  const toolbar = page.getByTestId("history-toolbar");
  await expectControlHeights(toolbar.locator("button, select, input"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='history-toolbar']",
    requireRows: true,
    tolerance: 1,
  });

  // HS-02: long titles clamp inside the row, never overflow the card.
  const title = page.locator(".history-row .history-row-card__title").first();
  await expect(title).toContainText("This history title");
  const titleMetrics = await title.evaluate((node) => ({
    overflow: getComputedStyle(node).overflow,
    scrollWidth: node.scrollWidth,
    clientWidth: node.clientWidth,
  }));
  expect(titleMetrics.overflow).toBe("hidden");
  expect(titleMetrics.scrollWidth).toBeGreaterThan(titleMetrics.clientWidth + 1);

  // HS-07: destructive actions keep the error semantics.
  await expect(page.getByTestId("history-clear")).toHaveClass(/btn--danger/);
  await expect(page.getByTestId("history-clear-progress")).toHaveClass(/btn--danger/);

  await toggle.locator('[data-view-mode="table"]').click();
  await expect(page.getByTestId("history-list")).toHaveAttribute("data-variant", "table");
  await expect(page.getByTestId("history-list-table")).toBeVisible();
  await expect(page.getByTestId("history-list-table")).toContainText("最近阅读");

  await toggle.locator('[data-view-mode="grid"]').click();
  await expect(page.getByTestId("history-list")).toHaveAttribute("data-variant", "grid");
  await expect(page.locator(".history-cell").first()).toBeVisible();

  await toggle.locator('[data-view-mode="list"]').click();
  await expect(page.getByTestId("history-list")).toHaveAttribute("data-variant", "list");

  expect(csp).toEqual([]);
});

test("@polish-series-history history has no horizontal overflow at 390", async ({ page }) => {
  await openHistory(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("history-list")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390);

  // HS-06: the row actions collapse to icons so the title keeps its width.
  const actions = page.locator(".history-row .history-actions").first();
  await expect(actions).toBeVisible();
  const label = actions.locator(".history-actions__label").first();
  const labelBox = await label.boundingBox();
  expect(labelBox === null || labelBox.width < 1).toBe(true);
});

test("@polish-series-history screenshots for series and history views", async ({ page }) => {
  await installLibManageMock(page);
  await mockFavDlBackend(page, { totalHistory: 12 });
  await installHistoryLongTitles(page);
  await installThumbStub(page);
  await page.goto("/#/series");

  const setMode = async (pageKey: string, mode: string) =>
    page.evaluate(
      ([key, value]) => {
        const raw = localStorage.getItem("gv_view_mode");
        let map: Record<string, string> = {};
        try {
          map = raw ? (JSON.parse(raw) as Record<string, string>) : {};
        } catch {
          map = {};
        }
        map[key] = value;
        localStorage.setItem("gv_view_mode", JSON.stringify(map));
      },
      [pageKey, mode],
    );

  await setMode("series", "grid");
  await shotMatrix(page, "series-grid", { url: "/#/series" });

  await setMode("series", "list");
  await shotMatrix(page, "series-list", { url: "/#/series" });

  await setMode("history", "list");
  await shotMatrix(page, "history-list", { url: "/#/history" });

  await setMode("history", "table");
  await shotMatrix(page, "history-table", { url: "/#/history" });

  await setMode("history", "grid");
  await shotMatrix(page, "history-grid", { url: "/#/history" });
});
