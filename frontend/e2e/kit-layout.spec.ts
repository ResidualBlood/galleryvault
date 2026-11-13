import { expect, test } from "./fixtures/mock";
import type { Page } from "@playwright/test";
import {
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

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

test("layout kit keeps one control ladder per toolbar row @kit-layout", async ({ page }) => {
  const csp = watchConsole(page);
  await page.goto("/#/_kit");

  const layout = page.getByTestId("kit-layout");
  await expect(layout).toBeVisible();
  await expect(layout.getByTestId("kit-page-header")).toBeVisible();

  // PageHeader uses the global headline-small step, not a local size.
  const typography = await page.evaluate(() => {
    const heading = document.querySelector('[data-testid="kit-page-header"] h1');
    const root = getComputedStyle(document.documentElement).fontSize;
    return {
      heading: heading ? parseFloat(getComputedStyle(heading).fontSize) : 0,
      root: parseFloat(root),
    };
  });
  expect(typography.heading).toBeCloseTo(typography.root * 1.5, 1);

  // Every control in the specimen toolbar is the same height and centreline.
  await expectRowsAligned(page, {
    rowSelector: '[data-testid="kit-layout-toolbar"]',
    requireRows: true,
  });
  const groupTops = await page
    .locator('[data-testid="kit-layout-toolbar"] [data-gv-toolbar-group]')
    .evaluateAll((groups) => groups.map((group) => Math.round(group.getBoundingClientRect().top)));
  expect(new Set(groupTops).size).toBe(1);

  await expect(page.getByTestId("gv-filter-badge")).toHaveText("3");

  // EmptyState delegates to Button, i.e. the control-lg step.
  const controlLg = await page.evaluate(() =>
    parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--gv-size-control-lg"),
    ),
  );
  const emptyButton = await page.getByTestId("kit-empty-action").boundingBox();
  expect(emptyButton?.height ?? 0).toBeCloseTo(controlLg, 0);

  // Pager rejects an out-of-range jump and keeps the current page.
  const jump = page.getByTestId("kit-pager").locator('[data-pager="jump"]');
  await jump.fill("999");
  await jump.press("Enter");
  await expect(page.getByTestId("kit-pager-current")).toHaveText("page 2");
  await expect(jump).toHaveValue("2");
  await expect(jump).toHaveAttribute("aria-invalid", "true");

  await jump.fill("3");
  await jump.press("Enter");
  await expect(page.getByTestId("kit-pager-current")).toHaveText("page 3");

  // Segmented control exposes radio semantics.
  const segmented = page.getByTestId("kit-segmented");
  await expect(segmented).toHaveAttribute("role", "radiogroup");
  await segmented.locator('[data-segmented-value="list"]').click();
  await expect(segmented.locator('[data-segmented-value="list"]')).toHaveAttribute(
    "aria-checked",
    "true",
  );

  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-layout"]' });
  await expectNoHorizontalOverflow(page);

  const shots = await shotMatrix(page, "kit-layout", { fullPage: true });
  expect(shots.files).toHaveLength(4);
  expect(csp).toEqual([]);
});

test("layout kit collapses groups into More at 390 @kit-layout", async ({ page }) => {
  const csp = watchConsole(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/_kit");
  await expect(page.getByTestId("kit-layout")).toBeVisible();

  // Collapsible groups leave the row; the More trigger replaces them.
  await expect(page.getByTestId("kit-layout-collapsible")).toHaveCount(0);
  const more = page.getByTestId("kit-layout-overflow-trigger");
  await expect(more).toBeVisible();

  // PageHeader actions drop below the title and stay right aligned.
  const geometry = await page.evaluate(() => {
    const header = document.querySelector('[data-testid="kit-page-header"]');
    const title = header?.querySelector("h1")?.getBoundingClientRect();
    const actions = header?.querySelector(".page-header__actions")?.getBoundingClientRect();
    return {
      titleBottom: title?.bottom ?? 0,
      actionsTop: actions?.top ?? 0,
      actionsRight: actions?.right ?? 0,
      headerRight: header?.getBoundingClientRect().right ?? 0,
    };
  });
  expect(geometry.actionsTop).toBeGreaterThanOrEqual(geometry.titleBottom);
  expect(geometry.actionsRight).toBeCloseTo(geometry.headerRight, 0);

  // The overflow menu really contains the collapsible group.
  await more.click();
  const sheet = page.getByTestId("kit-layout-overflow-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText("Import")).toBeVisible();
  await expect(sheet.getByText("Export")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();

  await expectNoHorizontalOverflow(page);
  await expectNoGlyphIcons(page, { selector: '[data-testid="kit-layout"]' });

  const shots = await shotMatrix(page, "kit-layout-compact", { fullPage: true });
  expect(shots.files).toHaveLength(4);
  expect(csp).toEqual([]);
});
