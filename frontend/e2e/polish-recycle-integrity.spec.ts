import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";
import { installMaintenanceMock } from "./fixtures/maintenance/mock";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
  freePort,
  watchCsp,
} from "./support/polish";
import { restoreGalleriesEp } from "@/api/recycle";
import { redownloadGalleryEp, scanIntegrityEp } from "@/api/integrity";

/**
 * po-recycle-integrity polish gate (batch 23).
 *
 * Closes the 14 audit defects of the recycle bin and the integrity check:
 *
 *   - RC-01 / IG-02 the empty state carries a body and one primary exit;
 *   - RC-02 the two source pills are the shared SegmentedControl with counts,
 *     one line of text and the chip height;
 *   - RC-03 / IG-03 destructive and disabled actions use the shared Button
 *     states (purge is a `danger` text action inside the selection bar);
 *   - RC-04 / IG-07 selection uses the shared 40px Checkbox, and the grid /
 *     list are the shared GalleryCard (same root class as the library);
 *   - RC-05 / IG-07 no self-written `minmax(180px)` grid: 390 opens as a list
 *     with `--gv-size-list-row` rows;
 *   - IG-01 scan is the single filled action; repair only appears with a
 *     selection and uses one label;
 *   - IG-04 the native `<details>` arrow is a registry chevron button;
 *   - IG-05 select-all is disabled with no rows; IG-06 the scan summary is
 *     independent of the list and also reaches the empty state;
 *   - RC-06 / IG-08 maintenance tabs stay on one scrollable line at 390.
 */

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

let vite: ViteDevServer;
let HARNESS = "";



function harnessUrl(path: string, options: { theme?: string; lang?: string } = {}): string {
  const params = new URLSearchParams();
  params.set("theme", options.theme ?? "dark");
  params.set("lang", options.lang ?? "zh");
  return `${HARNESS}?${params.toString()}#${path}`;
}

async function openRecycle(page: Page, options: { lang?: string } = {}): Promise<void> {
  await page.goto(harnessUrl("/recycle", options));
  await expect(page.getByTestId("recycle-view")).toBeVisible();
  await expect(page.getByTestId("recycle-item-21")).toBeVisible();
}

async function openIntegrity(page: Page): Promise<void> {
  await page.goto(harnessUrl("/integrity"));
  await expect(page.getByTestId("integrity-view")).toBeVisible();
  await expect(page.getByTestId("integrity-item-41")).toBeVisible();
}

async function switchView(page: Page, testid: string, mode: "grid" | "list"): Promise<void> {
  await page.getByTestId(testid).locator(`[data-view-mode="${mode}"]`).click();
}

/** Geometry of a toolbar row: ladder controls plus the segmented wrapper. */
async function toolbarMetrics(page: Page, testid: string) {
  return page.evaluate((id) => {
    const toolbar = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    if (!toolbar) return null;
    const nodes = [
      ...toolbar.querySelectorAll<HTMLElement>("[data-gv-control], .segmented"),
    ]
      .map((node) => node.getBoundingClientRect())
      .filter((rect) => rect.width > 1 && rect.height > 1);
    return {
      heights: nodes.map((rect) => Math.round(rect.height * 10) / 10),
      centers: nodes.map((rect) => Math.round((rect.top + rect.height / 2) * 10) / 10),
      box: toolbar.getBoundingClientRect().toJSON(),
    };
  }, testid);
}

async function controlLadder(page: Page): Promise<number[]> {
  return page.evaluate(() =>
    [
      ...document.querySelectorAll<HTMLElement>(
        'button, [data-gv-control], input:not([type="hidden"]), select',
      ),
    ]
      .filter((node) => {
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return (
          rect.width > 1 &&
          rect.height > 1 &&
          style.display !== "none" &&
          style.visibility !== "hidden"
        );
      })
      .map((node) => Math.round(node.getBoundingClientRect().height * 10) / 10),
  );
}

async function labelFontSizes(page: Page, selector: string): Promise<number[]> {
  return page.evaluate(
    (target) =>
      [...document.querySelectorAll<HTMLElement>(target)].map((node) =>
        Number.parseFloat(getComputedStyle(node).fontSize),
      ),
    selector,
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

test.beforeEach(async ({ page, baseURL }) => {
  const origin = baseURL ?? "http://127.0.0.1";
  await page.context().addCookies([
    { name: "galleryvault_csrf", value: "test-csrf", url: HARNESS },
    { name: "galleryvault_csrf", value: "test-csrf", url: origin },
  ]);
});

test("recycle toolbar, shared card, selection and tags are aligned @polish-recycle-integrity", async ({
  page,
}) => {
  const csp = watchCsp(page);
  const state = await installMaintenanceMock(page);
  await openRecycle(page);

  // The self-written `.recycle__card` is gone: every row is the shared card.
  await expect(page.locator('[data-testid="recycle-grid"] .gallery-card').first()).toBeVisible();
  await expect(page.locator(".recycle__card")).toHaveCount(0);
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "grid");

  // RC-02: one SegmentedControl with real counts, label-large text only.
  const segmented = page.getByTestId("recycle-tabs");
  await expect(segmented).toContainText("已删除 2");
  await expect(segmented).toContainText("已失踪 1");
  const segmentHeight = await page.evaluate(() =>
    Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--gv-size-control-md"),
    ),
  );
  const segmentedBox = await segmented.boundingBox();
  expect(segmentedBox!.height).toBeCloseTo(40, 0);
  await expectControlHeights(segmented.locator("[data-segmented-value]"), segmentHeight);
  const labelSizes = await labelFontSizes(page, '[data-testid="recycle-tabs"] .segmented__label');
  expect(labelSizes.length).toBeGreaterThan(0);
  expect(Math.min(...labelSizes)).toBeGreaterThan(11);

  // Toolbar ladder + one centre line (the segmented control keeps chip height
  // per DESIGN C17 and is centred against the lg buttons).
  await expectControlHeights(
    page.getByTestId("recycle-toolbar").locator("[data-gv-control]"),
    40,
  );
  const toolbar = await toolbarMetrics(page, "recycle-toolbar");
  expect(toolbar!.box.height).toBeLessThanOrEqual(56);
  expect(Math.max(...toolbar!.centers) - Math.min(...toolbar!.centers)).toBeLessThanOrEqual(1);

  await expectNoGlyphIcons(page, { selector: '[data-testid="recycle-view"]' });

  // RC-04: selection uses the shared Checkbox and shows the selection bar.
  await page.getByTestId("recycle-select-21").locator("input").check();
  const selection = page.getByTestId("recycle-selection");
  await expect(selection).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "recycle-selection-dark-1280.png") });
  const danger = page.getByTestId("recycle-purge");
  expect(await danger.getAttribute("class")).toContain("btn--danger");
  expect(await danger.evaluate((node) => Boolean(node.closest(".selection__danger")))).toBe(true);

  await page.getByTestId("recycle-restore").click();
  await expect
    .poll(
      () =>
        state.requests.filter(
          (request) =>
            request.method === "POST" && request.path === restoreGalleriesEp.path,
        ).at(-1)?.body,
    )
    .toMatchObject({ ids: [21] });
  await expect(page.getByTestId("recycle-selection")).toHaveCount(0);

  // Switch to the list: shared row, list-row token, inline tags + N.
  await switchView(page, "recycle-view-toggle", "list");
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "list");
  await expect(page.locator('[data-testid="recycle-item-21"] .gallery-list-row')).toBeVisible();
  const listHeight = await page
    .getByTestId("recycle-grid")
    .getAttribute("data-list-row-height");
  expect(Number(listHeight)).toBe(152);
  const chips = page.locator('[data-testid="recycle-item-21"] .tag-list .tag-chip');
  await expect(chips).toHaveCount(4);
  await expect(page.getByTestId("recycle-item-21").getByTestId("tag-more")).toHaveText("+2");

  // A tag click goes to the local library filter with tag_mode=and.
  await expect(chips.first()).toContainText("单女");
  await chips.first().click();
  await expect(page).toHaveURL(/#\/library\?/);
  expect(page.url()).toContain("tags=female");
  expect(page.url()).toContain("tag_mode=and");

  expect(csp).toEqual([]);
});

test("recycle tags use display in zh and the raw name in en @polish-recycle-integrity", async ({
  page,
}) => {
  await installMaintenanceMock(page);
  await openRecycle(page);
  await switchView(page, "recycle-view-toggle", "list");
  const firstChip = page.locator('[data-testid="recycle-item-21"] .tag-list .tag-chip').first();
  await expect(firstChip).toHaveText("单女");

  await page.goto(harnessUrl("/recycle", { lang: "en" }));
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "list");
  await expect(
    page.locator('[data-testid="recycle-item-21"] .tag-list .tag-chip').first(),
  ).toHaveText("sole female");
});

test("view mode is per page and 390 defaults to a list row @polish-recycle-integrity", async ({
  page,
}) => {
  await installMaintenanceMock(page);
  await openRecycle(page);
  await switchView(page, "recycle-view-toggle", "list");
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "list");

  await page.goto(harnessUrl("/integrity"));
  await expect(page.getByTestId("integrity-grid")).toHaveAttribute("data-variant", "grid");
  await switchView(page, "integrity-view-toggle", "list");
  await expect(page.getByTestId("integrity-grid")).toHaveAttribute("data-variant", "list");

  await page.goto(harnessUrl("/recycle"));
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "list");

  // A fresh context (no stored preference) opens 390 as a list.
  await page.evaluate(() => localStorage.removeItem("gv_view_mode"));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(harnessUrl("/recycle"));
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "list");
  const height = await page
    .getByTestId("recycle-grid")
    .getAttribute("data-list-row-height");
  expect(Number(height)).toBe(132);
  await expectNoHorizontalOverflow(page);
  await expectNoGlyphIcons(page, { selector: '[data-testid="recycle-view"]' });

  // RC-05: no 3:4 single-column card; the list row is the narrow default.
  await expect(page.locator('[data-testid="recycle-grid"] .gallery-card-list')).toHaveCount(2);
  await expect(page.locator('[data-testid="recycle-grid"] .gallery-card')).toHaveCount(0);
  await expect(page.locator('[data-testid="recycle-grid"] .gallery-list-row')).toHaveCount(2);
});

test("maintenance tabs stay on one scrollable line at 390 (RC-06/IG-08)", async ({
  page,
}) => {
  await installMaintenanceMock(page);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [path, view] of [
    ["/recycle", "recycle-view"],
    ["/integrity", "integrity-view"],
  ] as const) {
    await page.goto(harnessUrl(path));
    await expect(page.getByTestId(view)).toBeVisible();
    const tabs = page.getByTestId("maintenance-tabs");
    await expect(tabs.locator("[data-tab-value]")).toHaveCount(6);
    const tops = await tabs
      .locator("[data-tab-value]")
      .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().top)));
    expect(new Set(tops).size, `${path} tabs must not wrap`).toBe(1);
    const height = await tabs.evaluate((node) => ({
      scroll: node.scrollHeight,
      client: node.clientHeight,
    }));
    // Allow the 1px underline overflow; a wrapped strip would add a whole row.
    expect(height.scroll).toBeLessThanOrEqual(height.client + 2);
  }
});

test("recycle empty state explains and offers an exit @polish-recycle-integrity", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await installMaintenanceMock(page, { recycleEmpty: true });
  await page.goto(harnessUrl("/recycle"));
  const empty = page.getByTestId("recycle-empty");
  await expect(empty).toBeVisible();
  await expect(empty).toContainText("回收站是空的");
  await expect(empty).toContainText("保留 30 天");
  await expect(empty.getByTestId("recycle-empty-action")).toContainText("返回本机库");

  await empty.getByTestId("recycle-empty-action").click();
  await expect(page).toHaveURL(/#\/library/);
  expect(csp).toEqual([]);
  await expectNoHorizontalOverflow(page);
});

test("integrity scan, summary, disclosure and list alignment @polish-recycle-integrity", async ({
  page,
}) => {
  const csp = watchCsp(page);
  const state = await installMaintenanceMock(page);
  await openIntegrity(page);

  // IG-06: summary is independent of the list.
  await expect(page.getByTestId("integrity-summary")).toContainText("已扫描 10/12");
  await expect(page.getByTestId("integrity-summary")).toContainText("完成于");

  // IG-01 / IG-05: scan is the filled primary; select-all is a separate action.
  const scan = page.getByTestId("integrity-scan");
  expect(await scan.getAttribute("class")).toContain("btn--filled");
  await expect(page.getByTestId("integrity-select-all")).toBeEnabled();

  // IG-04: the native details arrow is gone, replaced by a registry chevron.
  const info = page.getByTestId("integrity-info-toggle");
  await expect(info).toHaveAttribute("aria-expanded", "false");
  await info.click();
  await expect(info).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("integrity-info")).toBeVisible();
  await expectNoGlyphIcons(page, { selector: '[data-testid="integrity-view"]' });

  // Toolbar rows stay on one ladder step and one centre line (no segmented
  // control on this page, so the shared support assertion applies directly).
  await expectRowsAligned(page, {
    rowSelector: '[data-testid="integrity-toolbar"]',
    requireRows: true,
  });
  await expectControlHeights(
    page.getByTestId("integrity-toolbar").locator("[data-gv-control]"),
    40,
  );

  // Selection bar only exists with a selection; repair is the single bulk label.
  await expect(page.getByTestId("integrity-repair")).toHaveCount(0);
  await page.getByTestId("integrity-select-41").locator("input").check();
  await expect(page.getByTestId("integrity-selection")).toBeVisible();
  await expect(page.getByTestId("integrity-repair")).toContainText("(1)");
  await page.screenshot({ path: join(SHOTS, "integrity-selection-dark-1280.png") });

  // IG-07: the list view shows the problem type as a badge and a sub-line.
  await switchView(page, "integrity-view-toggle", "list");
  await expect(page.getByTestId("integrity-grid")).toHaveAttribute("data-variant", "list");
  const row = page.getByTestId("integrity-item-41");
  await expect(row).toContainText("缺 3 页");
  await expect(row).toContainText("20 页 / 实际 17");
  const height = await page
    .getByTestId("integrity-grid")
    .getAttribute("data-list-row-height");
  expect(Number(height)).toBe(152);

  // Repairs are still wired to the existing endpoint.
  await page.getByTestId("integrity-repair").click();
  await expect
    .poll(
      () =>
        state.requests.filter(
          (request) =>
            request.method === "POST" && request.path === redownloadGalleryEp.path.replace("{id}", "41"),
        ).length,
    )
    .toBe(1);

  // IG-01: scan hits the existing endpoint once.
  await page.getByTestId("integrity-scan").click();
  await expect
    .poll(
      () =>
        state.requests.filter(
          (request) =>
            request.method === "POST" && request.path === scanIntegrityEp.path,
        ).length,
    )
    .toBe(1);

  expect(csp).toEqual([]);
});

test("integrity empty state keeps the scan result and primary action @polish-recycle-integrity", async ({
  page,
}) => {
  const csp = watchCsp(page);
  const state = await installMaintenanceMock(page, { integrityEmpty: true });
  await page.goto(harnessUrl("/integrity"));
  const empty = page.getByTestId("integrity-empty");
  await expect(empty).toBeVisible();
  await expect(page.getByTestId("integrity-select-all")).toBeDisabled();
  await expect(page.getByTestId("integrity-summary")).toHaveCount(0);
  await expect(empty).toContainText("已检查 10/12 个画廊");
  await expect(empty).toContainText("损坏 2 个");
  await expect(empty.getByTestId("integrity-empty-action")).toContainText("开始扫描");

  await empty.getByTestId("integrity-empty-action").click();
  await expect
    .poll(
      () =>
        state.requests.filter(
          (request) =>
            request.method === "POST" && request.path === scanIntegrityEp.path,
        ).length,
    )
    .toBe(1);
  expect(csp).toEqual([]);
  await expectNoHorizontalOverflow(page);
});

test("every control uses a control token step @polish-recycle-integrity", async ({ page }) => {
  await installMaintenanceMock(page);
  await openRecycle(page);
  const grid = await controlLadder(page);
  expect(grid.length).toBeGreaterThan(0);
  for (const height of grid) {
    expect(
      [24, 32, 36, 40].some((step) => Math.abs(height - step) <= 0.6),
      `control height ${height}px is not a control token step`,
    ).toBe(true);
  }
  await switchView(page, "recycle-view-toggle", "list");
  const list = await controlLadder(page);
  for (const height of list) {
    expect(
      [24, 32, 36, 40].some((step) => Math.abs(height - step) <= 0.6),
      `control height ${height}px is not a control token step`,
    ).toBe(true);
  }
});

test("four-variant screenshots for the recycle bin @polish-recycle-integrity", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await installMaintenanceMock(page);
  await openRecycle(page);
  await page.evaluate(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ recycle: "grid" })),
  );
  await page.reload();
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "grid");
  await shotMatrix(page, "recycle-grid");

  await page.evaluate(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ recycle: "list" })),
  );
  await page.reload();
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "list");
  await shotMatrix(page, "recycle-list");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(harnessUrl("/recycle"));
  await expect(page.getByTestId("recycle-grid")).toHaveAttribute("data-variant", "list");
  await shotMatrix(page, "recycle-390");
});

test("four-variant screenshots for the integrity check @polish-recycle-integrity", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await installMaintenanceMock(page);
  await openIntegrity(page);
  await page.evaluate(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ integrity: "grid" })),
  );
  await page.reload();
  await expect(page.getByTestId("integrity-grid")).toHaveAttribute("data-variant", "grid");
  await shotMatrix(page, "integrity-grid");

  await page.evaluate(() =>
    localStorage.setItem("gv_view_mode", JSON.stringify({ integrity: "list" })),
  );
  await page.reload();
  await expect(page.getByTestId("integrity-grid")).toHaveAttribute("data-variant", "list");
  await shotMatrix(page, "integrity-list");
});

test("four-variant screenshots for both empty states @polish-recycle-integrity", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await installMaintenanceMock(page, { recycleEmpty: true, integrityEmpty: true });
  await page.goto(harnessUrl("/recycle"));
  await expect(page.getByTestId("recycle-empty")).toBeVisible();
  await shotMatrix(page, "recycle-empty");

  await page.goto(harnessUrl("/integrity"));
  await expect(page.getByTestId("integrity-empty")).toBeVisible();
  await shotMatrix(page, "integrity-empty");
});
