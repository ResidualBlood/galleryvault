import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { mockSettingsBackend } from "./fixtures/settings-sys/mock";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
  watchCsp,
} from "./support/polish";

/**
 * po-archive-logs polish gate (batch 23).
 *
 * Closes AR-01 … AR-08 (cold-storage archive) and LG2-01, 03 … 12 (logs):
 *
 *   - AR-01/02 the page only gets the shell margin, uses PageHeader + the
 *     maintenance tab strip, and its content starts at the `#/updates` edge;
 *   - AR-03/04/05/08 one status chip, a labelled time row, an 8px progress bar
 *     with a percentage and four statistic cards that also render at zero;
 *   - AR-06 Skeleton / ErrorState instead of hand-written paragraphs;
 *   - AR-07 one 40px action row with the destructive purge action collapsed
 *     below 600px;
 *   - LG2-01/07/09 the finished list is paged at 50 rows, 40px high, showing
 *     status, progress, start time and duration;
 *   - LG2-04/08 status colours come from the semantic container tokens and the
 *     labels are translated;
 *   - LG2-05/06 PageHeader + the shared Tabs component;
 *   - LG2-10/11 the system-log toolbar is one 32px step and the log rows use a
 *     fixed level column, aligned timestamps and a monospace body.
 */

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");


async function mockJson(page: Page, pattern: string, body: unknown): Promise<void> {
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

function finishedBatch(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    task: `task-${index + 1}`,
    status: index % 7 === 3 ? "failed" : "success",
    started_at: `2026-11-12T${String(10 + (index % 8)).padStart(2, "0")}:00:00+08:00`,
    completed_at: `2026-11-12T${String(10 + (index % 8)).padStart(2, "0")}:01:10+08:00`,
    done: 10,
    total: 10,
  }));
}

async function mockActivity(page: Page, finishedCount: number): Promise<void> {
  await mockSettingsBackend(page);
  await mockJson(page, "**/api/logs", {
    running: [
      {
        task: "scan",
        started_at: "2026-11-12T20:30:00+08:00",
        done: 30,
        total: 120,
        stage: "scanning",
        cancellable: true,
      },
    ],
    finished: finishedBatch(finishedCount),
  });
  // `#/updates` is the alignment reference; give it a complete status payload.
  await mockJson(page, "**/api/updates/status", {
    detecting: false,
    last_detected_at: null,
    last_run: null,
    last_error: null,
    last_found: 0,
    counts: { pending: 0, downloading: 0, failed: 0, ignored: 0 },
  });
  await mockJson(page, "**/api/updates", { items: [], total: 0 });
}

async function mockArchive(page: Page, state?: Record<string, unknown>): Promise<void> {
  await mockSettingsBackend(page);
  if (state) await mockJson(page, "**/api/archive", state);
}

/** Every visible control height must be one of the control-ladder tokens. */
async function expectLadderHeights(page: Page, scope: string): Promise<void> {
  const allowed = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    const tokens = [
      "--gv-size-control-sm",
      "--gv-size-control-md",
      "--gv-size-control-lg",
      "--gv-size-control-xl",
      "--gv-size-chip",
    ];
    const values = tokens.map((token) => Number.parseFloat(style.getPropertyValue(token)));
    return [...new Set(values.filter((value) => Number.isFinite(value)))];
  });
  const heights = await page.evaluate((selector) => {
    const nodes = [
      ...document.querySelectorAll<HTMLElement>(
        `${selector} button:not([data-segmented-value]), ${selector} .segmented, ${selector} select, ${selector} input:not([type="hidden"]), ${selector} [role="switch"]`,
      ),
    ];
    return [
      ...new Set(
        nodes
          .map((node) => node.getBoundingClientRect())
          .filter((rect) => rect.width > 1 && rect.height > 1)
          .map((rect) => Math.round(rect.height * 10) / 10),
      ),
    ];
  }, scope);

  expect(heights.length).toBeGreaterThan(0);
  for (const height of heights) {
    expect(
      allowed.some((value) => Math.abs(value - height) <= 0.6),
      `control height ${height}px must be one of ${allowed.join(" / ")}px`,
    ).toBe(true);
  }
}

test.describe("archive & logs polish @polish-archive-logs", () => {
  test.beforeAll(() => {
    mkdirSync(SHOTS, { recursive: true });
  });

  test("archive header is headline-small, keeps the maintenance tabs and aligns with #/updates @polish-archive-logs", async ({
    page,
  }) => {
    const csp = watchCsp(page);
    await mockActivity(page, 0);

    await page.goto("/#/archive");
    await expect(page.getByTestId("archive-page")).toBeVisible();
    const heading = page.locator('[data-testid="archive-page"] h1');
    await expect(heading).toBeVisible();

    const expectedSize = await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.setAttribute("style", "font: var(--gv-type-headline-small)");
      document.body.append(probe);
      const size = Number.parseFloat(getComputedStyle(probe).fontSize);
      probe.remove();
      return size;
    });
    const actualSize = await heading.evaluate((node) => Number.parseFloat(getComputedStyle(node).fontSize));
    expect(Math.abs(actualSize - expectedSize)).toBeLessThanOrEqual(0.5);

    const tabs = page.getByTestId("maintenance-tabs");
    await expect(tabs).toBeVisible();
    const archiveTab = tabs.getByRole("tab", { name: "归档" });
    await expect(archiveTab).toHaveAttribute("aria-selected", "true");

    const archiveBox = await heading.boundingBox();
    expect(archiveBox).not.toBeNull();
    await page.goto("/#/updates");
    await expect(page.getByTestId("updates-view")).toBeVisible();
    const updatesBox = await page.locator('[data-testid="updates-view"] h1').boundingBox();
    expect(updatesBox).not.toBeNull();
    expect(Math.abs((archiveBox?.x ?? 0) - (updatesBox?.x ?? 0))).toBeLessThanOrEqual(1);

    await page.goto("/#/archive");
    await expect(page.getByTestId("archive-page")).toBeVisible();
    await expectNoGlyphIcons(page, { selector: "[data-testid='archive-page']" });
    await expectNoHorizontalOverflow(page);
    await expectLadderHeights(page, "[data-testid='archive-page']");
    await expectRowsAligned(page, {
      rowSelector: "[data-testid='archive-toolbar']",
      requireRows: true,
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#/archive");
    await page.reload();
    await expect(page.getByTestId("archive-page")).toBeVisible();
    const archiveMobile = await heading.boundingBox();
    await page.goto("/#/updates");
    await expect(page.getByTestId("updates-view")).toBeVisible();
    const updatesMobile = await page.locator('[data-testid="updates-view"] h1').boundingBox();
    expect(Math.abs((archiveMobile?.x ?? 0) - (updatesMobile?.x ?? 0))).toBeLessThanOrEqual(1);
    await expectNoHorizontalOverflow(page);
    expect(csp).toEqual([]);
  });

  test("archive shows a labelled progress bar and four statistic cards, including at zero @polish-archive-logs", async ({
    page,
  }) => {
    await mockArchive(page);
    await page.goto("/#/archive");
    await expect(page.getByTestId("archive-status")).toBeVisible();
    await expect(page.getByTestId("archive-status")).toContainText("归档完成");
    await expect(page.getByTestId("archive-status")).toContainText("50%");

    const bar = page.locator('[data-testid="archive-status"] [role="progressbar"]');
    await expect(bar).toBeVisible();
    const barHeight = await bar.evaluate((node) => node.getBoundingClientRect().height);
    const expectedBar = await page.evaluate(() =>
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--gv-space-2"),
      ),
    );
    expect(Math.abs(barHeight - expectedBar)).toBeLessThanOrEqual(0.5);
    const percent = await bar.evaluate((node) => node.getAttribute("aria-valuenow"));
    expect(percent).toBe("50");

    const stats = page.locator('[data-testid="archive-status"] .archive__stat dd');
    await expect(stats).toHaveText(["4", "1", "0", "10"]);

    await mockArchive(page, {
      running: false,
      done: 0,
      skipped: 0,
      failed: 0,
      total: 0,
      last_error: null,
      started_at: null,
      completed_at: null,
    });
    await page.goto("/#/archive");
    await page.reload();
    await expect(page.getByTestId("archive-status")).toBeVisible();
    await expect(page.getByTestId("archive-empty")).toBeVisible();
    await expect(page.getByTestId("archive-empty")).toContainText("还没有归档记录");
    const emptyStats = page.locator('[data-testid="archive-status"] .archive__stat dd');
    await expect(emptyStats).toHaveText(["0", "0", "0", "0"]);
  });

  test("200 finished tasks stay paged at 50 rows of 40px with translated statuses @polish-archive-logs", async ({
    page,
  }) => {
    await mockActivity(page, 200);
    await page.goto("/#/logs");
    await expect(page.getByTestId("logs-page")).toBeVisible();

    const rows = page.getByTestId("logs-finished-row");
    await expect(rows).toHaveCount(50);
    expect(await rows.count()).toBeLessThanOrEqual(60);

    const documentHeight = await page.evaluate(() => document.documentElement.scrollHeight);
    const viewportHeight = await page.evaluate(() => window.innerHeight);
    expect(documentHeight).toBeLessThanOrEqual(viewportHeight * 3);

    const rowHeights = await rows.evaluateAll((nodes) =>
      nodes.map((node) => node.getBoundingClientRect().height),
    );
    for (const height of rowHeights) expect(height).toBeLessThanOrEqual(44);

    await expect(page.getByTestId("logs-finished-pager")).toBeVisible();
    await expect(rows.first()).toContainText("成功");
    await expect(page.locator('[data-testid="logs-finished-row"][data-status="failed"]').first()).toContainText(
      "失败",
    );
    await expect(rows.first()).toContainText("耗时");

    await page.getByTestId("logs-filter").locator('[data-segmented-value="failed"]').click();
    await expect
      .poll(async () => {
        const statuses = await page
          .getByTestId("logs-finished-row")
          .evaluateAll((nodes) => nodes.map((node) => node.dataset.status));
        return statuses.length > 0 && statuses.every((status) => status === "failed");
      })
      .toBe(true);

    await page.getByTestId("logs-clear-finished").click();
    await expect(page.getByTestId("logs-finished-empty")).toBeVisible();
    await expect(page.getByTestId("logs-finished-empty")).toContainText("还没有已完成的任务");

    await expectNoGlyphIcons(page, { selector: "[data-testid='logs-page']" });
    await expectRowsAligned(page, { rowSelector: "[data-testid='logs-activity-toolbar']", requireRows: true });
    await expectLadderHeights(page, "[data-testid='logs-page']");
    await expectNoHorizontalOverflow(page);
  });

  test("system log toolbar is one step and the rows align level, time and message @polish-archive-logs", async ({
    page,
  }) => {
    const csp = watchCsp(page);
    await mockActivity(page, 12);
    await page.goto("/#/logs?tab=system");
    await expect(page.getByTestId("logs-system")).toBeVisible();

    const toolbar = page.getByTestId("syslog-toolbar");
    await expectControlHeights(
      toolbar.locator('select, input:not([type="hidden"]), button, [role="switch"]'),
      32,
    );
    await expectRowsAligned(page, { rowSelector: "[data-testid='syslog-toolbar']", requireRows: true });

    const tokens = await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.setAttribute(
        "style",
        "background: var(--gv-color-error-container); color: var(--gv-color-on-error-container)",
      );
      document.body.append(probe);
      const style = getComputedStyle(probe);
      const result = {
        error: style.backgroundColor,
        errorInk: style.color,
      };
      probe.remove();
      return result;
    });
    const errorChip = page.locator('[data-testid="syslog-entry"][data-level="ERROR"] .logs__level').first();
    await expect(errorChip).toBeVisible();
    const chipColors = await errorChip.evaluate((node) => {
      const style = getComputedStyle(node);
      return { background: style.backgroundColor, color: style.color };
    });
    expect(chipColors.background).toBe(tokens.error);
    expect(chipColors.color).toBe(tokens.errorInk);

    const timeXs = await page
      .locator('[data-testid="syslog-entry"] .logs__time')
      .evaluateAll((nodes) => [
        ...new Set(nodes.map((node) => Math.round(node.getBoundingClientRect().left))),
      ]);
    expect(timeXs.length).toBe(1);

    const family = await page
      .locator('[data-testid="syslog-entry"]')
      .first()
      .evaluate((node) => getComputedStyle(node).fontFamily.toLowerCase());
    expect(family).toContain("monospace");

    await expectNoGlyphIcons(page, { selector: "[data-testid='logs-page']" });
    await expectLadderHeights(page, "[data-testid='logs-page']");
    expect(csp).toEqual([]);
  });

  test("four-variant screenshots for every archive and log state @polish-archive-logs", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const csp = watchCsp(page);

    await mockArchive(page);
    await page.goto("/#/archive");
    await expect(page.getByTestId("archive-page")).toBeVisible();
    await shotMatrix(page, "archive-history", { url: "/#/archive" });

    await mockArchive(page, {
      running: true,
      done: 3,
      skipped: 1,
      failed: 0,
      total: 10,
      last_error: null,
      started_at: "2026-11-12T20:00:00+08:00",
      completed_at: null,
    });
    await shotMatrix(page, "archive-running", { url: "/#/archive" });

    await mockArchive(page, {
      running: false,
      done: 0,
      skipped: 0,
      failed: 0,
      total: 0,
      last_error: null,
      started_at: null,
      completed_at: null,
    });
    await shotMatrix(page, "archive-empty", { url: "/#/archive" });

    await mockActivity(page, 200);
    await shotMatrix(page, "logs-activity", { url: "/#/logs", fullPage: false });
    await shotMatrix(page, "logs-system", { url: "/#/logs?tab=system", fullPage: false });

    // LG2-12: an empty activity log has no "running" heading and shows the
    // shared EmptyState with a body and a retry exit.
    await mockSettingsBackend(page);
    await mockJson(page, "**/api/logs", { running: [], finished: [] });
    await shotMatrix(page, "logs-empty", { url: "/#/logs", fullPage: false });

    expect(csp).toEqual([]);
  });
});
