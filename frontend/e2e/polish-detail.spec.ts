import type { Page, Route } from "@playwright/test";
import { expect, test } from "./fixtures/mock";
import { mockGalleryBackend } from "./fixtures/gallery/mock";
import {
  SMALL_GALLERY_ID,
  SPARSE_GALLERY_ID,
} from "./fixtures/gallery/data";
import { mockOnlineBackend } from "./fixtures/online/mock";
import { detailResponse, LIST_GID, LIST_TOKEN } from "./fixtures/online/data";
import {
  expectControlHeights,
  expectNoGlyphIcons,
  expectNoHorizontalOverflow,
  expectRowsAligned,
  shotMatrix,
  watchCsp,
} from "./support/polish";

/**
 * Polish acceptance for the local + online gallery detail pages (batch 21).
 *
 * Every assertion is DOM-measured against the real preview build, so the
 * audit defects (GD-01..GD-10, OD-01..OD-12) are closed by behaviour rather
 * than by eyeballing screenshots. Screenshots are written to $GV_SHOTS so the
 * four theme x viewport variants referenced by closure.md exist.
 */

const LOCAL_URL = `/#/gallery/${SMALL_GALLERY_ID}`;
const SPARSE_URL = `/#/gallery/${SPARSE_GALLERY_ID}`;
const ONLINE_URL = `/#/online/g/${LIST_GID}/${LIST_TOKEN}`;

/** zh tag translations the backend would ship in `display`. */
const ZH_DISPLAY: Record<string, string> = {
  "fixture-artist": "示例画师",
  heroine: "女主角",
  "fixture-series": "示例系列",
  chinese: "中文",
  "full color": "全彩",
};

interface OnlineDetailVariant {
  /** Override the post date (OD-01 exercises an epoch value). */
  posted?: string | null;
  /** Add the backend `display` translations to every tag. */
  display?: boolean;
}

/**
 * Local overlay for the shared online fixture: the shared fixtures stay
 * untouched, and this suite only rewrites the detail payload fields it needs
 * to prove (post date, tag translations). Registered after `mockOnlineBackend`
 * so Playwright resolves it first.
 */
async function mockOnlineDetailVariant(
  page: Page,
  variant: OnlineDetailVariant = {},
): Promise<void> {
  await page.route("**/api/eh/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/^\/api\/eh\/galleries\/(\d+)\/([^/]+)$/);
    if (!match) {
      await route.fallback();
      return;
    }
    const payload = detailResponse(Number(match[1]), match[2]);
    if (payload.gallery) {
      if (variant.posted !== undefined) payload.gallery.posted = variant.posted;
      if (variant.display) {
        payload.gallery.tags = payload.gallery.tags.map((tag) => ({
          ...tag,
          display: ZH_DISPLAY[tag.name] ?? null,
        }));
      }
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}


async function controlStep(page: Page, token = "--gv-size-control-lg"): Promise<number> {
  return page.evaluate((name) => {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name);
    return Number.parseFloat(raw) || 40;
  }, token);
}

/**
 * GD-02 / OD-02 / OD-04: every visible control inside the action row is on the
 * same ladder step and shares one centre line. Anchors are included because
 * the two online navigation entries must not slip back to a hand-rolled pill.
 */
async function expectActionRow(page: Page, testid: string): Promise<void> {
  const row = page.getByTestId(testid);
  await expect(row).toBeVisible();

  const controls = row.locator(
    'button, a[href], input:not([type="hidden"]), [data-gv-control]',
  );
  const expected = await controlStep(page);
  await expectControlHeights(controls, expected);

  // expectRowsAligned only measures buttons / form controls, so the centre
  // lines (and the single-line guarantee) are also checked here, anchors
  // included.
  const measured = await page.evaluate((selector) => {
    const row = document.querySelector(selector);
    if (!row) return [] as Array<{ height: number; center: number }>;
    const nodes = [
      ...row.querySelectorAll<HTMLElement>(
        'button, a[href], input:not([type="hidden"]), [data-gv-control]',
      ),
    ];
    return nodes
      .map((node) => node.getBoundingClientRect())
      .filter((rect) => rect.width > 1 && rect.height > 1)
      .map((rect) => ({
        height: Math.round(rect.height * 10) / 10,
        center: Math.round((rect.top + rect.height / 2) * 10) / 10,
      }));
  }, `[data-testid="${testid}"]`);

  expect(measured.length).toBeGreaterThan(1);
  const centers = measured.map((entry) => entry.center);
  const heights = measured.map((entry) => entry.height);
  expect(
    Math.round((Math.max(...centers) - Math.min(...centers)) * 10) / 10,
    `action row centre lines differ: ${centers.join(", ")}`,
  ).toBeLessThanOrEqual(1);
  expect(
    Math.round((Math.max(...heights) - Math.min(...heights)) * 10) / 10,
    `action row heights differ: ${heights.join(", ")}`,
  ).toBe(0);

  await expectRowsAligned(page, {
    rowSelector: `[data-gv-toolbar="detail-actions"]`,
    requireRows: true,
    tolerance: 1,
  });

  await expectNoGlyphIcons(page, { selector: `[data-testid="${testid}"]` });
}

/**
 * "No orphan on the last meta row": a lone last cell must span the grid width,
 * which is how the two-column mobile layout keeps 5 or 7 facts readable.
 */
async function expectMetaGridFilled(page: Page): Promise<void> {
  const result = await page.evaluate(() => {
    const grids = [...document.querySelectorAll<HTMLElement>('[data-testid="detail-meta"]')];
    const violations: string[] = [];
    for (const grid of grids) {
      const items = [
        ...grid.querySelectorAll<HTMLElement>('[data-testid="detail-meta-item"]'),
      ];
      if (items.length < 3) continue;
      const gridWidth = grid.getBoundingClientRect().width;
      const rows = new Map<number, HTMLElement[]>();
      for (const item of items) {
        const top = Math.round(item.getBoundingClientRect().top);
        rows.set(top, [...(rows.get(top) ?? []), item]);
      }
      const tops = [...rows.keys()].sort((a, b) => a - b);
      const last = rows.get(tops[tops.length - 1] ?? 0) ?? [];
      if (last.length === 1) {
        const width = last[0]?.getBoundingClientRect().width ?? 0;
        if (width < gridWidth * 0.9) {
          violations.push(
            `last meta row holds one ${Math.round(width)}px cell inside a ${Math.round(gridWidth)}px grid`,
          );
        }
      }
    }
    return { grids: grids.length, violations };
  });
  expect(result.grids, "the detail page must render a meta grid").toBeGreaterThan(0);
  expect(result.violations).toEqual([]);
}

async function expectHeaderContract(
  page: Page,
  titleTestid: string,
  crumbLabel: string,
): Promise<void> {
  const heading = page.getByTestId(titleTestid);
  await expect(heading).toBeVisible();
  await expect(heading).toHaveJSProperty("tagName", "H1");
  await expect(page.getByTestId("detail-back")).toBeVisible();
  await expect(page.locator(".page-header__crumbs")).toContainText(crumbLabel);
}

test.describe("polish: gallery detail pages @polish-detail", () => {
  test("local detail: header, meta grid, aligned action row, four screenshots @polish-detail", async ({
    page,
  }) => {
    const csp = watchCsp(page);
    await mockGalleryBackend(page);
    await page.goto(LOCAL_URL);
    await expect(page.getByTestId("gallery-detail")).toBeVisible();

    await expectHeaderContract(page, "gallery-title", "本机库");
    await expect(page.getByTestId("gallery-title")).toHaveText("Small Detail Fixture");
    await expectNoGlyphIcons(page);
    await expectActionRow(page, "detail-actions");
    await expectMetaGridFilled(page);
    await expectNoHorizontalOverflow(page);

    // GD-08: the management actions are all on the `sm` step (the CBZ entry is
    // a download link, so it is measured together with the buttons).
    await expectControlHeights(
      page.locator(
        '[data-gv-toolbar="manage-actions"] button, [data-gv-toolbar="manage-actions"] a[href]',
      ),
      await controlStep(page, "--gv-size-control-sm"),
    );

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(LOCAL_URL);
    await expect(page.getByTestId("gallery-detail")).toBeVisible();
    await expectActionRow(page, "detail-actions");
    await expectMetaGridFilled(page);
    await expectNoHorizontalOverflow(page);

    await shotMatrix(page, "po-detail-local", { url: LOCAL_URL });
    expect(csp).toEqual([]);
  });

  test("online detail: header, aligned action row with link entries, four screenshots @polish-detail", async ({
    page,
  }) => {
    const csp = watchCsp(page);
    await mockOnlineBackend(page);
    await mockOnlineDetailVariant(page, { display: true });
    await page.goto(ONLINE_URL);
    await expect(page.getByTestId("online-detail-view")).toBeVisible();
    await expect(page.getByTestId("online-title")).toHaveText("Online Detail Fixture");

    await expectHeaderContract(page, "online-title", "在线");
    await expectNoGlyphIcons(page);
    await expectActionRow(page, "online-actions");
    await expectMetaGridFilled(page);
    await expectNoHorizontalOverflow(page);

    // OD-12: the official entry stays a real link (href/target/rel) but sits
    // on the same control step as the buttons.
    const official = page.getByTestId("online-official");
    await expect(official).toHaveAttribute("href", /exhentai\.org\/g\//);
    await expect(official).toHaveAttribute("target", "_blank");
    await expect(official).toHaveAttribute("rel", "noopener noreferrer");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(ONLINE_URL);
    await expect(page.getByTestId("online-detail-view")).toBeVisible();
    await expectActionRow(page, "online-actions");
    await expectMetaGridFilled(page);
    await expectNoHorizontalOverflow(page);

    await shotMatrix(page, "po-detail-online", { url: ONLINE_URL });
    expect(csp).toEqual([]);
  });

  test("390: favourite and download stay above the fixed bottom bar @polish-detail", async ({
    page,
  }) => {
    await mockGalleryBackend(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(LOCAL_URL);
    await expect(page.getByTestId("gallery-detail")).toBeVisible();

    const viewport = page.viewportSize() ?? { width: 390, height: 844 };
    const navbar = await page.evaluate(() => {
      const raw = getComputedStyle(document.documentElement).getPropertyValue(
        "--gv-size-navbar",
      );
      return Number.parseFloat(raw) || 80;
    });
    const limit = viewport.height - navbar;

    for (const testid of ["continue-reading", "fav-button", "download-button"]) {
      const box = await page.getByTestId(testid).boundingBox();
      expect(box, `${testid} must be laid out`).toBeTruthy();
      if (!box) continue;
      expect(
        Math.ceil(box.y + box.height),
        `${testid} bottom ${Math.round(box.y + box.height)} must stay above ${limit}`,
      ).toBeLessThanOrEqual(limit);
    }

    const actionBox = await page.getByTestId("detail-actions").boundingBox();
    if (actionBox) {
      expect(Math.ceil(actionBox.y + actionBox.height)).toBeLessThanOrEqual(limit);
    }

    await shotMatrix(page, "po-detail-390-actions", { url: LOCAL_URL });
  });

  test("a zero / epoch post date reads 未知, never 1970 @polish-detail", async ({ page }) => {
    await mockGalleryBackend(page);
    await mockOnlineBackend(page);

    await page.goto(SPARSE_URL);
    await expect(page.getByTestId("gallery-detail")).toBeVisible();
    const localPosted = page
      .getByTestId("detail-meta-item")
      .filter({ hasText: "上传时间" });
    await expect(localPosted).toHaveCount(1);
    await expect(localPosted).toContainText("未知");
    await expect(page.locator("body")).not.toContainText("1970");
    await shotMatrix(page, "po-detail-local-unknown", { url: SPARSE_URL });

    await mockOnlineDetailVariant(page, { posted: "1970-01-22T00:00:00Z" });
    await page.goto(ONLINE_URL);
    await expect(page.getByTestId("online-detail-view")).toBeVisible();
    const onlinePosted = page
      .getByTestId("detail-meta-item")
      .filter({ hasText: "发布时间" });
    await expect(onlinePosted).toHaveCount(1);
    await expect(onlinePosted).toContainText("未知");
    await expect(page.locator("body")).not.toContainText("1970");
    await shotMatrix(page, "po-detail-online-unknown", { url: ONLINE_URL });
  });

  test("tag click filters the library / re-runs the online search @polish-detail", async ({
    page,
  }) => {
    await mockGalleryBackend(page);
    await page.goto(LOCAL_URL);
    const localChip = page.getByTestId("tag-chip").filter({ hasText: "阿尔法" });
    await expect(localChip).toHaveCount(1);
    await localChip.click();
    await expect(page).toHaveURL(/#\/library\?/);
    await expect
      .poll(async () => decodeURIComponent(await page.evaluate(() => location.hash)))
      .toContain("tags=artist:alpha");
    expect(
      decodeURIComponent(await page.evaluate(() => location.hash)),
    ).toContain("tag_mode=and");

    await mockOnlineBackend(page);
    await mockOnlineDetailVariant(page, { display: true });
    await page.goto(ONLINE_URL);
    const onlineChip = page.getByTestId("tag-chip").filter({ hasText: "全彩" });
    await expect(onlineChip).toHaveCount(1);
    await onlineChip.click();
    await expect(page).toHaveURL(/#\/online\?/);
    await expect
      .poll(async () =>
        decodeURIComponent(await page.evaluate(() => location.hash)).replace(/\+/g, " "),
      )
      .toContain('q=misc:"full color$"');
  });

  test("switching language re-labels tags without a new detail request @polish-detail", async ({
    page,
  }) => {
    let detailRequests = 0;
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (/^\/api\/galleries\/\d+$/.test(path)) detailRequests += 1;
    });

    await mockGalleryBackend(page);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(LOCAL_URL);
    await expect(page.getByTestId("gallery-title")).toBeVisible();

    const chip = page.getByTestId("tag-chip").filter({ hasText: "阿尔法" });
    await expect(chip).toHaveCount(1);
    const before = detailRequests;

    await page.getByTestId("lang-toggle").click();
    const english = page.getByTestId("tag-chip").filter({ hasText: "alpha" });
    await expect(english).toHaveCount(1);
    await expect(page.getByTestId("tag-chip").filter({ hasText: "阿尔法" })).toHaveCount(0);
    expect(detailRequests, "language switch must not refetch the detail").toBe(before);
  });

  test("online tag labels follow the locale without a detail refetch @polish-detail", async ({
    page,
  }) => {
    let detailRequests = 0;
    page.on("request", (request) => {
      if (/^\/api\/eh\/galleries\/\d+\/[^/]+$/.test(new URL(request.url()).pathname)) {
        detailRequests += 1;
      }
    });

    await mockOnlineBackend(page);
    await mockOnlineDetailVariant(page, { display: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(ONLINE_URL);
    await expect(page.getByTestId("online-title")).toBeVisible();

    await expect(
      page.getByTestId("tag-chip").filter({ hasText: "示例画师" }),
    ).toHaveCount(1);
    const before = detailRequests;

    await page.getByTestId("lang-toggle").click();
    await expect(
      page.getByTestId("tag-chip").filter({ hasText: "fixture-artist" }),
    ).toHaveCount(1);
    await expect(page.getByTestId("tag-chip").filter({ hasText: "示例画师" })).toHaveCount(0);
    expect(detailRequests, "language switch must not refetch the detail").toBe(before);
  });
});
