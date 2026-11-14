import { expect, test } from "./fixtures/mock";
import type { Page, Route } from "@playwright/test";
import { archiveEp, restoreArchivesEp } from "@/api/archive";
import { galleriesEp } from "@/api/galleries";
import { logsEp } from "@/api/system";
import { installLibraryMock } from "./fixtures/library/seed";
import { mockGalleryBackend } from "./fixtures/gallery/mock";
import { COLD_GALLERY_ID } from "./fixtures/gallery/data";
import { watchCsp } from "./support/polish";

/**
 * T4.4 cold-storage UI gate.
 *
 *   - the library storage filter round-trips URL ↔ `storage_tier`;
 *   - the detail page shows the cold badge + cold date only for archived rows,
 *     and the manage section confirms before asking the backend to unarchive;
 *   - the archive page lists the cold library, links to the filtered list and
 *     restores the checked rows through `POST /api/archive/restore`;
 *   - the logs page translates the `unarchive` task name.
 */

interface ColdBackendState {
  restored: number[] | null;
}

function coldItem(id: number, title: string, pages: number) {
  return {
    id,
    gid: 900000 + id,
    token: `cold-${id}`,
    title,
    storage_type: "folder",
    storage_tier: "cold",
    cold_at: "2026-11-02T09:00:00Z",
    category: "doujinshi",
    page_count: pages,
    cover_url: null,
    tags: [],
    uploader: "fixture",
    posted_at: "2026-10-01T00:00:00Z",
    file_size: pages * 1024 * 1024,
    storage_size: pages * 1024 * 1024,
    rating: null,
    favorite: false,
    favorite_category: null,
    reading_progress: 0,
    expunged: false,
    image_quality: "original",
    local_rating: null,
    local_note: null,
  };
}

async function json(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/** Archive cold section + logs task name backend. */
async function installColdBackend(page: Page): Promise<ColdBackendState> {
  const state: ColdBackendState = { restored: null };
  const COLD = [
    coldItem(301, "Cold One", 12),
    coldItem(302, "Cold Two", 24),
  ];

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === archiveEp.path && request.method() === "GET") {
      await json(route, 200, { running: false });
      return;
    }
    if (path === galleriesEp.path && url.searchParams.get("storage_tier") === "cold") {
      await json(route, 200, {
        total: COLD.length,
        page: 1,
        page_size: 100,
        q: "",
        tags: "",
        resolved: false,
        tag_mode: "and",
        tag_match: "exact",
        order_by: "id_desc",
        read_status: "all",
        category: "",
        items: COLD,
      });
      return;
    }
    if (path === restoreArchivesEp.path && request.method() === "POST") {
      const body = JSON.parse(request.postData() ?? "{}") as { ids?: number[] };
      state.restored = body.ids ?? [];
      await json(route, 202, { status: "started", total: state.restored.length });
      return;
    }
    if (path === logsEp.path) {
      await json(route, 200, {
        running: [],
        finished: [
          {
            task: "unarchive",
            status: "success",
            started_at: "2026-11-14T10:00:00+08:00",
            completed_at: "2026-11-14T10:00:08+08:00",
            done: 2,
            total: 2,
          },
        ],
      });
      return;
    }
    await route.fallback();
  });
  return state;
}

test("library storage filter round-trips storage_tier in URL and request @cold-ui", async ({
  page,
}) => {
  const csp = watchCsp(page);
  const state = await installLibraryMock(page, { total: 12 });

  await page.goto("/#/library?storage_tier=cold");
  await expect(page.getByTestId("library-view")).toBeVisible();
  await expect(page.getByTestId("active-filter-chip")).toContainText("存储：冷库");
  await expect
    .poll(() => state.requests.at(-1)?.get("storage_tier"), { timeout: 10_000 })
    .toBe("cold");

  await expect(page.getByTestId("advanced-filters")).toBeVisible();
  await page
    .getByTestId("storage-tier-filter")
    .locator("select")
    .selectOption("hot");

  await expect(page).toHaveURL(/storage_tier=hot/);
  await expect(page.getByTestId("active-filter-chip")).toContainText("存储：热库");
  await expect
    .poll(() => state.requests.at(-1)?.get("storage_tier"), { timeout: 10_000 })
    .toBe("hot");

  expect(csp).toEqual([]);
});

test("cold detail shows the badge and restores after confirmation @cold-ui", async ({
  page,
}) => {
  const csp = watchCsp(page);
  await mockGalleryBackend(page);
  let restores = 0;
  await page.route(`**/api/galleries/${COLD_GALLERY_ID}/unarchive`, async (route) => {
    restores += 1;
    await json(route, 202, { status: "started", id: COLD_GALLERY_ID });
  });

  await page.goto(`/#/gallery/${COLD_GALLERY_ID}`);
  await expect(page.getByTestId("gallery-detail")).toBeVisible();
  await expect(page.getByTestId("cold-badge")).toHaveText("冷库");
  await expect(page.getByTestId("gallery-detail")).toContainText("冷库时间");

  await page.getByTestId("restore-to-hot").click();
  const dialog = page.getByTestId("restore-to-hot-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("下载目录");
  await expect(dialog).toContainText("删除冷包");
  expect(restores).toBe(0);

  await page.getByTestId("restore-to-hot-confirm").click();
  await expect.poll(() => restores).toBe(1);
  expect(csp).toEqual([]);
});

test("archive cold section restores the selected rows @cold-ui", async ({ page }) => {
  const csp = watchCsp(page);
  const state = await installColdBackend(page);

  await page.goto("/#/archive");
  await expect(page.getByTestId("archive-cold-count")).toContainText("冷库 2 本");
  await expect(page.getByTestId("archive-cold-row")).toHaveCount(2);

  await page.getByTestId("archive-cold-view").click();
  await expect(page).toHaveURL(/storage_tier=cold/);

  await page.goto("/#/archive");
  await expect(page.getByTestId("archive-cold-row")).toHaveCount(2);
  const rows = page.getByTestId("archive-cold-row");
  await rows.nth(0).locator('input[type="checkbox"]').check();
  await rows.nth(1).locator('input[type="checkbox"]').check();
  await expect(page.getByTestId("archive-cold-selection")).toContainText("2");

  await page.getByTestId("archive-cold-restore").click();
  const dialog = page.getByTestId("archive-cold-restore-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("删除冷包");
  await page.getByTestId("archive-cold-restore-confirm").click();

  await expect.poll(() => state.restored).toEqual([301, 302]);
  expect(csp).toEqual([]);
});

test("logs translate the unarchive task @cold-ui", async ({ page }) => {
  await installColdBackend(page);
  await page.goto("/#/logs");
  await expect(page.getByTestId("logs-finished-list")).toBeVisible();
  await expect(page.getByTestId("logs-finished-list")).toContainText("冷库还原");
});
