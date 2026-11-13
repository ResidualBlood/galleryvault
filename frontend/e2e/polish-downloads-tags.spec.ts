import { mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Locator, Page } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import {
  clearSuccessfulDownloadsEp,
  createDownloadBatchEp,
  downloadsEp,
  pauseEp,
  quotaEp,
  retryAllDownloadsEp,
} from "@/api/downloads";
import { reloadTagsEp, startTagSyncEp, tagsSearchEp } from "@/api/library";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
} from "./support/polish";

/**
 * po-downloads-tags polish gate (audit rows TG-01 … TG-07, DL-01 … DL-09).
 *
 * Downloads:
 *   - DL-01 the add row is one 40px ladder step with a shared centre line;
 *   - DL-02 filters collapsed into one segmented control + a "more" menu, and
 *     batch actions only exist while something is selected;
 *   - DL-03 / DL-06 / DL-09 no character icons, row actions are IconButtons on
 *     the sm step and never wrap onto their own line at 390, titles clamp to
 *     two lines there;
 *   - DL-04 / DL-05 every task row is the same height with a status icon and
 *     colour, and a finished task no longer offers retry.
 *
 * Tags:
 *   - TG-01 / TG-02 one 40px toolbar row without the 442px hole;
 *   - TG-03 / TG-05 / TG-07 every namespace and tag label is translated and the
 *     cloud is grouped by namespace, no raw key reaches the visible text;
 *   - TG-04 / TG-06 chip-height namespace row with one-line scrolling and the
 *     shared Pager.
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

const TASKS = [
  {
    id: 1,
    gid: 800001,
    title: "Sunset Sketchbook — a very long title that has to be clipped at 390",
    status: "downloading",
    retry_count: 0,
    current_page: 12,
    total_pages: 40,
    error_message: null,
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_fallback: false,
    speed: 1_572_864,
    eta_seconds: 95,
  },
  {
    id: 2,
    gid: 800002,
    title: "Night Market Diaries",
    status: "pending",
    retry_count: 0,
    current_page: 0,
    total_pages: null,
    error_message: null,
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_fallback: false,
  },
  {
    id: 3,
    gid: 800003,
    title: "Archive Collection Vol. 3",
    status: "success",
    retry_count: 0,
    current_page: 120,
    total_pages: 120,
    error_message: null,
    mode: "favorite_archive",
    quality: "original",
    archive_status: "ok",
    archive_fallback: false,
  },
  {
    id: 4,
    gid: 800004,
    title: "Gone Gallery",
    status: "failed",
    retry_count: 3,
    current_page: 0,
    total_pages: null,
    error_message: "GalleryGoneError: deleted or not found",
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_fallback: false,
  },
  {
    id: 5,
    gid: 800005,
    title: "Cancelled Download",
    status: "cancelled",
    retry_count: 1,
    current_page: 4,
    total_pages: 30,
    error_message: null,
    mode: "gallery",
    quality: "resample",
    archive_status: null,
    archive_fallback: false,
  },
];

const TAG_ITEMS = [
  { namespace: "artist", name: "alpha", display: "阿尔法", usage_count: 80 },
  { namespace: "artist", name: "beta", display: "贝塔", usage_count: 40 },
  { namespace: "female", name: "sole female", display: "单体女性", usage_count: 300 },
  { namespace: "male", name: "sole male", display: "单体男性", usage_count: 210 },
  { namespace: "uploader", name: "nightowl", display: "夜猫子上传", usage_count: 12 },
  { namespace: "reclass", name: "moved", display: "已重分类", usage_count: 3 },
  { namespace: "temp", name: "scratch", display: "临时标签", usage_count: 1 },
];

const FACETS = [
  { namespace: "female", total: 300 },
  { namespace: "male", total: 210 },
  { namespace: "artist", total: 80 },
  { namespace: "uploader", total: 41 },
  { namespace: "reclass", total: 1 },
  { namespace: "temp", total: 1 },
];

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

async function installMock(page: Page): Promise<void> {
  let paused = false;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (path === pauseEp.path) {
      if (method === "POST") {
        const body = request.postDataJSON() as { paused?: boolean } | null;
        paused = Boolean(body?.paused);
      }
      await json({ paused });
      return;
    }
    if (path === quotaEp.path) {
      await json({
        gp: 12_345,
        image_limit: { current: 86, limit: 100 },
        image_limits: { current: 86, limit: 100 },
        checked_at: "2026-11-13T10:30:00Z",
        error: null,
        cached: true,
      });
      return;
    }
    if (path === downloadsEp.path && method === "GET") {
      const status = url.searchParams.get("status");
      const filtered = status ? TASKS.filter((task) => task.status === status) : TASKS;
      const pageNo = Number.parseInt(url.searchParams.get("page") ?? "1", 10) || 1;
      const pageSize = Number.parseInt(url.searchParams.get("page_size") ?? "24", 10) || 24;
      const start = (pageNo - 1) * pageSize;
      await json({
        total: filtered.length,
        page: pageNo,
        page_size: pageSize,
        items: filtered.slice(start, start + pageSize),
      });
      return;
    }
    if (path === createDownloadBatchEp.path) {
      await json({ queued: 1, skipped: 0, gone: 0, updated: 0, failed: 0, items: [] });
      return;
    }
    if (path === clearSuccessfulDownloadsEp.path) {
      await json({ deleted: 1 });
      return;
    }
    if (path === retryAllDownloadsEp.path) {
      await json({ retried_count: 1, count: 1, task_ids: [4] });
      return;
    }
    if (/\/(?:cancel|retry)$/.test(path)) {
      await json({});
      return;
    }
    if (method === "DELETE" && path.startsWith(`${downloadsEp.path}/`)) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === tagsSearchEp.path) {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const namespace = url.searchParams.get("namespace") ?? "";
      const pageSize = Number.parseInt(url.searchParams.get("page_size") ?? "100", 10) || 100;
      let items = TAG_ITEMS;
      if (q) items = items.filter((item) => item.name.includes(q));
      if (namespace) items = items.filter((item) => item.namespace === namespace);
      await json({
        total: items.length,
        page: Number.parseInt(url.searchParams.get("page") ?? "1", 10) || 1,
        page_size: pageSize,
        facets: pageSize === 1 ? FACETS : [],
        items,
      });
      return;
    }
    if (path === reloadTagsEp.path) {
      await json({ accepted: true, ok: true, last_error: null }, 202);
      return;
    }
    if (path === startTagSyncEp.path) {
      await json({ status: "started", queued: 3 }, 202);
      return;
    }

    await route.fallback();
  });
}

function roundedBoxes(root: Locator, selector: string) {
  return root.locator(selector).evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        height: Math.round(rect.height),
        width: Math.round(rect.width),
        center: Math.round(rect.top + rect.height / 2),
      };
    }),
  );
}

async function openDownloads(page: Page): Promise<void> {
  await installMock(page);
  await page.goto("/#/downloads");
  await expect(page.getByTestId("downloads-view")).toBeVisible();
  await expect(page.getByTestId("downloads-list")).toBeVisible();
}

async function openTags(page: Page): Promise<void> {
  await installMock(page);
  await page.goto("/#/tags");
  await expect(page.getByTestId("tags-view")).toBeVisible();
  await expect(page.getByTestId("tags-cloud")).toBeVisible();
}

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

test("@polish-downloads-tags downloads: one-step add row, segmented filters and a quiet toolbar", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await openDownloads(page);

  // DL-03: no Unicode glyph anywhere — pause is an SVG from the registry.
  await expectNoGlyphIcons(page, { selector: "[data-testid='downloads-view']" });
  const pause = page.getByTestId("downloads-pause");
  await expect(pause.locator("svg.gv-icon")).toHaveCount(1);
  await expect(pause).not.toContainText("⏸");
  await expect(pause).not.toContainText("▶");

  // DL-01: Select + both buttons share the 40px step and one centre line.
  const addRow = page.getByTestId("downloads-add-actions");
  await expectControlHeights(addRow.locator("button, select"), 40);
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='downloads-add-actions']",
    requireRows: true,
  });
  const addControls = await roundedBoxes(addRow, "button, select");
  expect(new Set(addControls.map((box) => box.center)).size).toBe(1);

  // DL-02: the six status filters are one segmented control, and the global
  // maintenance actions live behind the overflow menu.
  const segmented = page.getByTestId("downloads-status-segmented");
  await expect(segmented.locator("[data-segmented-value]")).toHaveCount(6);
  const segmentSize = await page.evaluate(() =>
    Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--gv-size-control-md"),
    ),
  );
  await expectControlHeights(segmented.locator("[data-segmented-value]"), segmentSize);
  await expect(page.getByTestId("downloads-retry-all")).toHaveCount(0);
  await expect(page.getByTestId("downloads-clear-success")).toHaveCount(0);
  await page.getByTestId("downloads-more-trigger").click();
  await expect(page.getByTestId("downloads-retry-all")).toBeVisible();
  await expect(page.getByTestId("downloads-clear-success")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("downloads-retry-all")).toHaveCount(0);

  // DL-02: batch actions are invisible until something is selected.
  await expect(page.getByTestId("downloads-selection")).toHaveCount(0);
  await expect(page.getByTestId("downloads-delete-selected")).toHaveCount(0);
  await page.getByTestId("downloads-select-all").click();
  await expect(page.getByTestId("downloads-selection")).toBeVisible();
  await expect(page.getByTestId("downloads-delete-selected")).toBeVisible();
  await page.getByTestId("downloads-selection").getByTestId("gv-selection-clear").click();
  await expect(page.getByTestId("downloads-selection")).toHaveCount(0);

  // DL-04 / DL-05: equal-height rows, status icon + colour, no retry on success.
  const rows = page.locator("[data-testid='downloads-list'] .download-item");
  await expect(rows).toHaveCount(5);
  const heights = await rows.evaluateAll((nodes) =>
    nodes.map((node) => Math.round(node.getBoundingClientRect().height)),
  );
  expect(new Set(heights).size, `task rows must be equal height: ${heights.join("/")}`).toBe(1);
  await expect(rows.locator(".download-item__state svg.gv-icon")).toHaveCount(5);
  const success = page.locator('.download-item[data-status="success"]');
  await expect(success.getByTestId("downloads-retry")).toHaveCount(0);
  await expect(success.getByTestId("downloads-delete")).toBeVisible();
  const failed = page.locator('.download-item[data-status="failed"]');
  await expect(failed.getByTestId("downloads-retry")).toBeVisible();
  const successColor = await success
    .locator(".download-item__state")
    .evaluate((node) => getComputedStyle(node).color);
  const failedColor = await failed
    .locator(".download-item__state")
    .evaluate((node) => getComputedStyle(node).color);
  expect(successColor).not.toBe(failedColor);

  // DL-06: row-end actions are icon buttons without visible text.
  const actions = await page
    .locator("[data-testid='downloads-list'] .download-item__actions button")
    .evaluateAll((nodes) =>
      nodes.map((node) => ({
        text: (node.textContent ?? "").trim(),
        icons: node.querySelectorAll("svg.gv-icon").length,
      })),
    );
  expect(actions.length).toBeGreaterThan(0);
  for (const action of actions) {
    expect(action.text).toBe("");
    expect(action.icons).toBe(1);
  }

  expect(csp).toEqual([]);
});

test("@polish-downloads-tags downloads: 390 keeps filters and row actions on one line", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await openDownloads(page);

  await expectNoHorizontalOverflow(page);
  await expectNoGlyphIcons(page, { selector: "[data-testid='downloads-view']" });

  // DL-07: the segmented control is a single scrollable line, never 5 + 1.
  const segments = await roundedBoxes(
    page.getByTestId("downloads-status-segmented"),
    "[data-segmented-value]",
  );
  expect(segments).toHaveLength(6);
  expect(new Set(segments.map((box) => box.top)).size).toBe(1);
  await expectControlHeights(
    page.getByTestId("downloads-status-segmented").locator("[data-segmented-value]"),
    await page.evaluate(() =>
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--gv-size-control-md"),
      ),
    ),
  );

  // The add row still fits one line at 390 (DL-01).
  await expectRowsAligned(page, {
    rowSelector: "[data-testid='downloads-add-actions']",
    requireRows: true,
  });

  // DL-06 / DL-09: actions stay beside the body (never a second row) and the
  // titles clamp to two lines so same-series tasks stay distinguishable.
  const rows = page.locator("[data-testid='downloads-list'] .download-item");
  const count = await rows.count();
  expect(count).toBe(5);
  for (let index = 0; index < count; index += 1) {
    const row = rows.nth(index);
    const rowBox = (await row.boundingBox())!;
    const mainBox = (await row.locator(".download-item__main").boundingBox())!;
    const actionsBox = (await row.locator(".download-item__actions").boundingBox())!;
    expect(actionsBox.x, "row actions must sit beside the body").toBeGreaterThanOrEqual(
      mainBox.x + mainBox.width - 1,
    );
    expect(
      Math.abs(actionsBox.y + actionsBox.height / 2 - (rowBox.y + rowBox.height / 2)),
      "row actions must stay on the row centre line",
    ).toBeLessThanOrEqual(1);
    expect(await row.locator(".download-item__title").evaluate((node) => getComputedStyle(node).webkitLineClamp)).toBe(
      "2",
    );
  }
  const heights = await rows.evaluateAll((nodes) =>
    nodes.map((node) => Math.round(node.getBoundingClientRect().height)),
  );
  expect(new Set(heights).size, `390 rows must be equal height: ${heights.join("/")}`).toBe(1);

  expect(csp).toEqual([]);
});

test("@polish-downloads-tags downloads: every status renders its own icon and progress", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await openDownloads(page);

  // One screenshot per state, since the audit only ever saw "已完成".
  const states = ["downloading", "pending", "success", "failed", "cancelled"] as const;
  for (const state of states) {
    await page
      .getByTestId("downloads-status-segmented")
      .locator(`[data-segmented-value="${state}"]`)
      .click();
    await expect(page.locator(".download-item")).toHaveCount(1);
    const row = page.locator(".download-item").first();
    await expect(row).toHaveAttribute("data-status", state);
    await expect(row.locator(".download-item__state svg.gv-icon")).toHaveCount(1);
    await page.emulateMedia({ colorScheme: "dark" });
    await page.evaluate(() => localStorage.setItem("gv_theme", "dark"));
    await page.screenshot({
      path: join(SHOTS, `downloads-state-${state}-dark-1280.png`),
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: "light" });
    await page.evaluate(() => localStorage.setItem("gv_theme", "light"));
    await page.reload();
    await expect(page.locator(".download-item")).toHaveCount(1);
    await page.screenshot({
      path: join(SHOTS, `downloads-state-${state}-light-390.png`),
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.evaluate(() => localStorage.setItem("gv_theme", "dark"));
    await page.reload();
    await expect(page.locator(".download-item")).toHaveCount(1);
  }

  // A running task shows the 4px track with a width plus speed / ETA.
  await page
    .getByTestId("downloads-status-segmented")
    .locator('[data-segmented-value="downloading"]')
    .click();
  const meta = page.getByTestId("downloads-task-meta").first();
  await expect(meta).toContainText("12/40");
  await expect(meta).toContainText("1.5 MB/s");
  await expect(page.locator('[data-status="downloading"] .download-item__fill')).toHaveCount(1);

  expect(csp).toEqual([]);
});

test("@polish-downloads-tags tags: translated namespaces, grouped cloud and chip filtering", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await openTags(page);

  await expectNoGlyphIcons(page, { selector: "[data-testid='tags-view']" });

  // TG-03: no raw namespace key or `ns:` prefix reaches the visible text.
  const text = await page.getByTestId("tags-view").innerText();
  expect(text).not.toMatch(/uploader|reclass|temp\b/i);
  expect(text).not.toContain("artist:");
  await expect(page.getByTestId("tags-ns-uploader")).toContainText("上传者");
  await expect(page.getByTestId("tags-ns-reclass")).toContainText("重分类");
  await expect(page.getByTestId("tags-ns-temp")).toContainText("临时");

  // TG-04: namespace chips use the chip token height and scroll on one line.
  const chipToken = await page.evaluate(() =>
    Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--gv-size-chip"),
    ),
  );
  const pill = page.getByTestId("tags-ns-artist");
  const pillBox = await pill.boundingBox();
  expect(Math.round(pillBox!.height)).toBe(Math.round(chipToken));
  const pillTops = await roundedBoxes(
    page.getByTestId("tags-namespaces"),
    "[data-testid^='tags-ns-']",
  );
  expect(new Set(pillTops.map((box) => box.top)).size).toBe(1);

  // TG-01 / TG-02: one 40px toolbar row, no 442px hole in the middle.
  await expectControlHeights(page.getByTestId("tags-toolbar").locator("button, input"), 40);
  await expectRowsAligned(page, { rowSelector: "[data-testid='tags-toolbar']", requireRows: true });
  const searchBox = await page.getByTestId("tags-search-input").boundingBox();
  const searchForm = await page.locator(".tags__search").boundingBox();
  const reloadBox = await page.getByTestId("tags-reload").boundingBox();
  expect(searchBox!.width).toBeGreaterThan(300);
  // The search form fills the left side, so the old 442px gap is gone.
  expect(reloadBox!.x - (searchForm!.x + searchForm!.width)).toBeLessThan(40);

  // TG-05: the cloud is grouped by namespace with a heading per group.
  const groups = page.locator("[data-testid='tags-cloud'] [data-group]");
  expect(await groups.count()).toBeGreaterThan(1);
  const mismatched = await page
    .locator("[data-testid='tags-cloud'] [data-group]")
    .evaluateAll((nodes) =>
      nodes
        .map((node) => ({
          group: node.getAttribute("data-group"),
          chips: [...node.querySelectorAll("[data-namespace]")].map((chip) =>
            chip.getAttribute("data-namespace"),
          ),
        }))
        .filter((entry) => entry.chips.some((chip) => chip !== entry.group)),
    );
  expect(mismatched).toEqual([]);

  // TG-06: the shared Pager replaced the three text buttons.
  await expect(page.getByTestId("tags-pager")).toBeVisible();
  await expect(page.getByTestId("tags-pager").locator('[data-pager="prev"]')).toBeVisible();

  // Clicking a chip filters the local library with the AND contract.
  await page.locator("[data-testid='tags-cloud'] [data-namespace]").first().click();
  await expect(page).toHaveURL(/#\/library\?tags=/);
  await expect(page).toHaveURL(/tag_mode=and/);
  await expect(page).toHaveURL(/tags=[a-z]+(%3A|:)/);

  expect(csp).toEqual([]);
});

test("@polish-downloads-tags tags: switching language re-labels namespaces and tags offline", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await installMock(page);
  let tagRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === tagsSearchEp.path) tagRequests += 1;
  });
  await page.goto("/#/tags");
  await expect(page.getByTestId("tags-cloud")).toBeVisible();
  await expect(page.getByTestId("tags-ns-uploader")).toContainText("上传者");

  const before = tagRequests;
  await page.getByTestId("lang-toggle").click();
  await expect(page.getByTestId("tags-ns-uploader")).toContainText("Uploader");
  const firstChip = page.locator("[data-testid='tags-cloud'] [data-namespace='artist']").first();
  await expect(firstChip).toContainText("alpha");
  await expect(firstChip).not.toContainText("阿尔法");
  expect(tagRequests, "locale switching must not refetch tags").toBe(before);

  // The tooltip keeps the i18n namespace title plus the raw `ns:name`.
  await expect(firstChip).toHaveAttribute("title", /Artist/);
  await expect(firstChip).toHaveAttribute("title", /artist:alpha/);

  expect(csp).toEqual([]);
});

test("@polish-downloads-tags four-variant screenshots", async ({ page }) => {
  await installMock(page);
  await page.goto("/#/downloads");
  await expect(page.getByTestId("downloads-list")).toBeVisible();
  const downloads = await shotMatrix(page, "downloads");
  expect(downloads.files).toHaveLength(4);

  await page.goto("/#/tags");
  await expect(page.getByTestId("tags-cloud")).toBeVisible();
  const tags = await shotMatrix(page, "tags");
  expect(tags.files).toHaveLength(4);
});
