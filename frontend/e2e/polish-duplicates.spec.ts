import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { installMaintenanceMock, type MaintenanceMockState } from "./fixtures/maintenance/mock";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

/**
 * po-duplicates polish gate (batch 23, audit rows FM-01 … FM-06, FI-01 … FI-04,
 * DP-01 … DP-09, DX-01 … DX-09).
 *
 * The four duplicate views share one skeleton: PageHeader → maintenance tabs →
 * a 40px action toolbar → a separate 32px filter toolbar (so no row mixes the
 * two ladder steps) → SelectionBar (favourites / cross-gid / ignored) →
 * DuplicateGroupCard + DuplicateCopyRow → Pager, with EmptyState actions.
 *
 * Assertions are DOM-measured:
 *   - one control-ladder step per toolbar, one row per toolbar at 1280;
 *   - no character icons; no horizontal overflow at 390;
 *   - a group title keeps ≥160px at 390 and the copy row stays horizontal;
 *   - batch / destructive actions only exist in the SelectionBar, danger last;
 *   - the ignored page is a secondary view with a back button, no wrong tab;
 *   - empty states always carry one primary exit;
 *   - cross-gid external links still go through safeHref and the shell marks
 *     the duplicate navigation entry active.
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

async function open(page: Page, path: string, root: string): Promise<MaintenanceMockState> {
  const state = await installMaintenanceMock(page);
  await page.goto(`/#${path}`);
  await expect(page.getByTestId(root)).toBeVisible({ timeout: 20_000 });
  return state;
}

async function buttonCount(page: Page): Promise<number> {
  return (
    (await page.getByTestId("duplicates-toolbar").locator("button").count()) +
    (await page.getByTestId("duplicates-filters").locator("button").count())
  );
}

async function box(page: Page, selector: string) {
  const value = await page.locator(selector).first().boundingBox();
  expect(value, `missing ${selector}`).toBeTruthy();
  return value!;
}

async function fontSizes(page: Page, selector: string): Promise<number> {
  return page.locator(selector).first().evaluate((node) => {
    return Number.parseFloat(getComputedStyle(node).fontSize);
  });
}

async function segmentItemStep(page: Page): Promise<number> {
  return page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return Number.parseFloat(style.getPropertyValue("--gv-size-control-sm")) - 4;
  });
}

test("@polish-duplicates library duplicates: two uniform toolbars, shared group and copy rows", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await open(page, "/duplicates", "duplicates-view");
  await expect(page.getByTestId("duplicates-group-9001")).toContainText("Alpha Copy");
  await expectNoGlyphIcons(page, { selector: "[data-testid='duplicates-view']" });

  // FM-01 / DP-02 / DX-02: actions are all lg, filters use the 32px frame (28px segments), and
  // the two toolbar rows never mix steps.
  await expectControlHeights(page.getByTestId("duplicates-toolbar").locator("button"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='duplicates-toolbar']",
    requireRows: true,
  });
  const segment = await segmentItemStep(page);
  await expectControlHeights(
    page.getByTestId("duplicates-filters").locator("[data-segmented-value]"),
    segment,
  );
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='duplicates-filters']",
    requireRows: true,
  });
  expect(await buttonCount(page)).toBeLessThanOrEqual(5);

  // DP-01 / DP-03 / DP-09: one header row for gid/title, one for chips/action;
  // chips share the 32px control step with the group action, and the gid is
  // set in the smaller label step.
  const header = page.getByTestId("duplicates-group-9001").locator("header").first();
  const headerHeights = await header.evaluate((node) =>
    [...node.querySelectorAll(".dup-badge, button")].map((el) =>
      Math.round(el.getBoundingClientRect().height),
    ),
  );
  expect(new Set(headerHeights)).toEqual(new Set([32]));
  expect(await fontSizes(page, ".dup-group__gid")).toBeLessThan(
    await fontSizes(page, ".dup-group__title"),
  );
  await expect(header).toContainText("保留首个");
  await expect(header).not.toContainText("keep first");

  // DP-04 / DP-05 / DP-07: localized policy, tonal keep vs danger delete, tags
  // rendered by the shared 24px TagList with a +N overflow.
  const copy = page.getByTestId("duplicates-copy-copy-a");
  await expect(copy).toContainText("当前保留");
  await expect(copy).toContainText("巨乳");
  const keep = copy.getByTestId("duplicates-keep-copy-a");
  const keepDelete = copy.getByTestId("duplicates-keep-delete-copy-a");
  await expect(keep).toHaveClass(/btn--tonal/);
  await expect(keepDelete).toHaveClass(/btn--danger/);
  await expectControlHeights(copy.locator(".dup-copy__actions button"), 32);
  const tagHeights = await copy
    .locator(".tag-chip")
    .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().height)));
  expect(tagHeights.length).toBeGreaterThan(0);
  expect(new Set(tagHeights)).toEqual(new Set([24]));

  await expectNoHorizontalOverflow(page);
  await shotMatrix(page, "duplicates-library", { url: `${page.url()}` });
  expect(csp).toEqual([]);
});

test("@polish-duplicates favourite duplicates: filters split, danger only in the selection bar", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await open(page, "/duplicates/favorites", "dupfav-view");
  await expect(page.getByTestId("dupfav-group-fav-group-1")).toBeVisible();
  await expectNoGlyphIcons(page, { selector: "[data-testid='dupfav-view']" });

  await expectControlHeights(page.getByTestId("dupfav-toolbar").locator("button"), 40);
  await expectRowsAligned(page, { rowSelector: "[data-testid='dupfav-toolbar']", requireRows: true });
  await expectControlHeights(
    page.getByTestId("dupfav-filters").locator("[data-segmented-value]"),
    await segmentItemStep(page),
  );
  await expectRowsAligned(page, { rowSelector: "[data-testid='dupfav-filters']", requireRows: true });

  // FM-02 / FM-06: the ignored page entry lives in the header, not as a naked
  // link at the end of the toolbar; batch actions appear only with a selection.
  await expect(page.getByTestId("dupfav-ignored-link")).toBeVisible();
  await expect(page.getByTestId("dupfav-selection")).toHaveCount(0);
  await expect(page.getByTestId("dupfav-unfav")).toHaveCount(0);
  await page.getByTestId("dupfav-select-3002").locator("input").check();
  const bar = page.getByTestId("dupfav-selection");
  await expect(bar).toBeVisible();
  const danger = bar.locator(".selection__danger .btn--danger");
  await expect(danger).toHaveCount(2);
  await expect(danger.last()).toContainText("取消收藏并删除已下载");
  await expect(bar.locator(".selection__danger")).toContainText("取消收藏");
  await page.getByTestId("gv-selection-clear").click();
  await expect(bar).toHaveCount(0);

  await expectNoHorizontalOverflow(page);
  await shotMatrix(page, "duplicates-favorites", { url: page.url() });
  expect(csp).toEqual([]);
});

test("@polish-duplicates cross-gid duplicates: safe links, icon disclosure and active navigation", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await open(page, "/duplicates/cross-gid", "dupxgid-view");
  await expect(page.getByTestId("dupxgid-item-5001")).toBeVisible();
  await expectNoGlyphIcons(page, { selector: "[data-testid='dupxgid-view']" });

  // DX-01 / DX-02: one action row and one filter row, all controls uniform.
  await expectControlHeights(page.getByTestId("dupxgid-toolbar").locator("button"), 40);
  await expectRowsAligned(page, { rowSelector: "[data-testid='dupxgid-toolbar']", requireRows: true });
  await expectControlHeights(
    page.getByTestId("dupxgid-filters").locator("[data-segmented-value]"),
    await segmentItemStep(page),
  );
  await expectRowsAligned(page, { rowSelector: "[data-testid='dupxgid-filters']", requireRows: true });

  // DX-04 / DX-07: disclosure and group collapse are icon buttons, not glyphs
  // or a native <details> triangle.
  await expect(page.locator("details")).toHaveCount(0);
  const collapse = page.getByTestId("dupxgid-collapse").first();
  await expect(collapse.locator("svg.gv-icon")).toHaveCount(1);
  await expect(collapse).toHaveAttribute("aria-expanded", "true");
  await collapse.click();
  await expect(collapse).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByTestId("dupxgid-item-5001")).toBeHidden();
  await collapse.click();
  await page.getByTestId("dupxgid-info-toggle").click();
  await expect(page.getByTestId("dupxgid-info-toggle")).toHaveAttribute("aria-expanded", "true");

  // DX-08: "22 页" and translated storage/category, never "22 P" or raw keys.
  const local = page.getByTestId("dupxgid-item-5001");
  await expect(local).toContainText("22 页");
  await expect(local).toContainText("文件夹");
  const cloud = page.getByTestId("dupxgid-item-5002");
  await expect(cloud).toContainText("同人志");
  await expect(page.getByText("22 P")).toHaveCount(0);

  // Existing safeHref contract: the javascript: URL becomes a harmless hash.
  await expect(page.getByTestId("dupxgid-link-5002")).toHaveAttribute("href", "#");
  expect(await page.locator('a[href^="javascript:"]').count()).toBe(0);

  // DX-05: the shell keeps "duplicates" active on the cross-gid child route.
  await expect(page.locator('[data-nav="app.nav.duplicates"]').first()).toHaveClass(/router-link-active/);

  await page.getByTestId("dupxgid-select-5002").locator("input").check();
  await expect(page.getByTestId("dupxgid-selection")).toBeVisible();
  await page.getByTestId("gv-selection-clear").click();

  await expectNoHorizontalOverflow(page);
  await shotMatrix(page, "duplicates-cross-gid", { url: page.url() });
  expect(csp).toEqual([]);
});

test("@polish-duplicates ignored duplicates: secondary view with back, no wrong tab", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await open(page, "/favorites/ignored", "favignored-view");
  await expect(page.getByTestId("favignored-item-4001")).toBeVisible();
  await expectNoGlyphIcons(page, { selector: "[data-testid='favignored-view']" });

  // FI-01 / FI-02 / FI-04: no maintenance tab bar (so nothing can be
  // highlighted wrongly) and an explicit back affordance in the header.
  await expect(page.getByTestId("maintenance-tabs")).toHaveCount(0);
  const header = page.getByTestId("favignored-header");
  await expect(header).toContainText("已忽略的收藏重复");
  const back = header.getByRole("button").first();
  await expect(back).toBeVisible();

  await page.getByTestId("favignored-select-0").click();
  await expect(page.getByTestId("favignored-selection")).toBeVisible();
  await expect(page.getByTestId("favignored-restore-selected")).toBeVisible();

  await expectNoHorizontalOverflow(page);
  await shotMatrix(page, "duplicates-ignored", { url: page.url() });

  await back.click();
  await expect(page.getByTestId("dupfav-view")).toBeVisible();
  await expect(page).toHaveURL(/#\/favorites\/manage/);
  expect(csp).toEqual([]);
});

test("@polish-duplicates tabs stay on one scrollable line at 390 and group titles stay readable", async ({
  page,
}) => {
  await open(page, "/duplicates", "duplicates-view");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("duplicates-group-9001")).toBeVisible({ timeout: 20_000 });

  // FM-04 / DP-08 / DX-09: all six tabs share one top edge; the bar scrolls
  // instead of wrapping into two ragged rows.
  const tabTops = await page
    .getByTestId("maintenance-tabs")
    .locator("[role='tab']")
    .evaluateAll((nodes) =>
      nodes.map((node) => Math.round(node.getBoundingClientRect().top * 10) / 10),
    );
  expect(tabTops.length).toBe(6);
  expect(new Set(tabTops).size).toBe(1);

  // DP-01: the group title keeps a readable visible width.
  const title = await box(page, "[data-testid='duplicates-group-9001'] .dup-group__title");
  expect(title.width).toBeGreaterThanOrEqual(160);

  // DP-06: the copy row stays horizontal and clamps the title to two lines.
  const row = page.getByTestId("duplicates-copy-copy-b");
  const direction = await row.evaluate((node) => getComputedStyle(node).flexDirection);
  expect(direction).toBe("row");
  const clamp = await row
    .locator(".dup-copy__title-text")
    .evaluate((node) => getComputedStyle(node).webkitLineClamp);
  expect(clamp).toBe("2");

  // No mixed-height row survives the breakpoint either.
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='duplicates-toolbar']",
    requireRows: true,
  });
  await expectNoHorizontalOverflow(page);
  await shotMatrix(page, "duplicates-library-390", { url: page.url() });
});

test("@polish-duplicates empty states carry one primary exit on all four views", async ({ page }) => {
  const csp = watchCsp(page);
  await installMaintenanceMock(page, {
    duplicatesEmpty: true,
    favoritesEmpty: true,
    ignoredEmpty: true,
    crossGidEmpty: true,
  });

  await page.goto("/#/duplicates");
  const libraryEmpty = page.getByTestId("duplicates-empty");
  await expect(libraryEmpty).toBeVisible({ timeout: 20_000 });
  await expect(libraryEmpty).toContainText("扫描库");
  await expect(page.getByTestId("duplicates-empty-action")).toBeVisible();
  await shotMatrix(page, "duplicates-library-empty", { url: page.url() });

  await page.goto("/#/duplicates/favorites");
  const favoritesEmpty = page.getByTestId("dupfav-empty");
  await expect(favoritesEmpty).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("dupfav-empty-action")).toBeVisible();
  await shotMatrix(page, "duplicates-favorites-empty", { url: page.url() });

  await page.goto("/#/duplicates/cross-gid");
  const crossEmpty = page.getByTestId("dupxgid-empty");
  await expect(crossEmpty).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("dupxgid-empty-action")).toContainText("重新计算");
  await shotMatrix(page, "duplicates-cross-gid-empty", { url: page.url() });

  await page.goto("/#/favorites/ignored");
  const ignoredEmpty = page.getByTestId("favignored-empty");
  await expect(ignoredEmpty).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("favignored-empty-action")).toContainText("返回收藏夹重复");
  await shotMatrix(page, "duplicates-ignored-empty", { url: page.url() });

  expect(csp).toEqual([]);
});

test("@polish-duplicates cross-gid not-computed state is a title, body and primary action", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await installMaintenanceMock(page, { crossGidNotReady: true });
  await page.goto("/#/duplicates/cross-gid");
  const hint = page.getByTestId("dupxgid-hint");
  await expect(hint).toBeVisible({ timeout: 20_000 });
  await expect(hint).toContainText("尚未跨 GID 查重");
  await expect(page.getByTestId("dupxgid-hint-action")).toContainText("重新计算");
  await expectNoHorizontalOverflow(page);
  await shotMatrix(page, "duplicates-cross-gid-hint", { url: page.url() });
  expect(csp).toEqual([]);
});
