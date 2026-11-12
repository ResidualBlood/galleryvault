import { readerPageMetaEp, readerPagePath } from "../src/api/reader";
import { expect, test } from "./fixtures/mock";
import {
  GAP_ONLINE_ITEMS,
  GAP_READER_GALLERY_ID,
  installGapsMock,
} from "./fixtures/gaps/mock";

test("updates archive uses the shared preview dialog @gaps", async ({ page }) => {
  const state = await installGapsMock(page);
  await page.goto("/#/updates");
  await expect(page.getByTestId("updates-view")).toBeVisible();

  await page.getByTestId("updates-select-1").check();
  await page.getByTestId("updates-archive").click();

  const dialog = page.getByTestId("archive-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("GP 余额");
  await expect(dialog).toContainText("Archive 900001");
  await expect
    .poll(() => state.previews.at(-1)?.gids)
    .toEqual([900001]);

  await dialog.locator("select").selectOption("original");
  await page.getByTestId("archive-dialog-confirm").click();

  await expect
    .poll(() => state.updateBodies.at(-1))
    .toMatchObject({ ids: [1], archive: true, quality: "original" });
});

test("favorites archive uses the shared preview dialog @gaps", async ({ page }) => {
  const state = await installGapsMock(page);
  await page.goto("/#/favorites/0");
  await expect(page.getByTestId("favlist-grid")).toBeVisible();

  const cards = page.getByTestId("favlist-grid").locator("article");
  await cards.nth(0).locator('input[type="checkbox"]').check();
  await cards.nth(1).locator('input[type="checkbox"]').check();
  await page.getByTestId("favlist-archive").click();

  const dialog = page.getByTestId("archive-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Archive 800001");
  await expect
    .poll(() => state.previews.at(-1)?.gids)
    .toEqual([800001, 800002]);

  await dialog.locator("select").selectOption("original");
  await page.getByTestId("archive-dialog-confirm").click();

  await expect
    .poll(() => state.favoriteDownloads.at(-1))
    .toMatchObject({
      gids: [800001, 800002],
      archive: true,
      quality: "original",
    });
});

test("library advanced filters sync URL and request parameters @gaps", async ({ page }) => {
  const state = await installGapsMock(page);
  await page.goto("/#/library");
  await expect(page.getByTestId("library-grid")).toBeVisible();

  await page.getByTestId("advanced-toggle").click();
  await expect(page.getByTestId("advanced-filters")).toBeVisible();

  await page.getByTestId("page-min").locator("input").fill("20");
  await page.getByTestId("page-max").locator("input").fill("80");
  await page.getByTestId("size-min").locator("input").fill("5");
  await page.getByTestId("min-rating").locator("select").selectOption("4");
  await page.getByTestId("library-search-submit").click();

  await expect(page).toHaveURL(/page_min=20/);
  await expect(page).toHaveURL(/page_max=80/);
  await expect(page).toHaveURL(/size_min=5/);
  await expect(page).toHaveURL(/min_rating=4/);

  await expect
    .poll(() => {
      const params = state.galleryCalls.at(-1);
      return {
        page_min: params?.get("page_min") ?? null,
        page_max: params?.get("page_max") ?? null,
        size_min: params?.get("size_min") ?? null,
        min_rating: params?.get("min_rating") ?? null,
      };
    })
    .toEqual({
      page_min: "20",
      page_max: "80",
      size_min: String(5 * 1048576),
      min_rating: "4",
    });

  await page.getByTestId("language-filter").locator("select").selectOption("chinese");
  await expect(page).toHaveURL(/tags=language(%3A|:)/);
  await expect
    .poll(() => state.galleryCalls.at(-1)?.get("tags"))
    .toBe("language:chinese");

  await page.reload();
  await expect(page.getByTestId("library-grid")).toBeVisible();
  await expect(page.getByTestId("advanced-filters")).toBeVisible();
  await expect(page.getByTestId("page-min").locator("input")).toHaveValue("20");
  await expect(page.getByTestId("size-min").locator("input")).toHaveValue("5");
});

test("library card quick actions and batch delete reload @gaps", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("gv_default_favcat", "0");
  });
  const state = await installGapsMock(page);
  await page.goto("/#/library");
  await expect(page.getByTestId("library-grid")).toBeVisible();

  await page.getByTestId("fav-100001").getByTestId("fav-button").click();
  await expect
    .poll(() => state.favoriteAdds.at(-1)?.items[0]?.gid)
    .toBe(100001);
  await expect(page.getByTestId("fav-100001").getByTestId("fav-button")).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  const callsBefore = state.galleryCalls.length;
  const cards = page.getByTestId("library-card");
  await cards.nth(0).locator('input[type="checkbox"]').check();
  await cards.nth(1).locator('input[type="checkbox"]').check();
  await page.getByTestId("batch-delete").click();
  await page.getByTestId("batch-delete-confirm").click();
  await page.getByTestId("batch-delete-confirm").click();

  await expect.poll(() => state.deletedBulk.length).toBe(1);
  expect(state.deletedBulk[0]?.ids).toEqual([1, 2]);
  await expect
    .poll(() => state.galleryCalls.length)
    .toBeGreaterThan(callsBefore);

  await expect(page.getByTestId("gallery-card")).toHaveCount(2);
  const ids = await page
    .getByTestId("gallery-card")
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-id")));
  expect(ids).toEqual(["3", "4"]);
});

test("online list batch download and favourite follow cloud results @gaps2", async ({
  page,
}) => {
  const state = await installGapsMock(page);
  state.batchFavoriteCloudFailed.add(GAP_ONLINE_ITEMS[1].gid);
  await page.goto("/#/online");
  await expect(page.getByTestId("online-grid")).toHaveAttribute("data-loaded", "3");

  const cards = page.getByTestId("online-card");
  await cards.nth(0).locator('input[type="checkbox"]').check();
  await cards.nth(1).locator('input[type="checkbox"]').check();
  await expect(page.getByTestId("online-selected-count")).toContainText("2");

  await page.getByTestId("online-batch-download").click();
  await expect
    .poll(() => state.downloadBatches.at(-1)?.items)
    .toEqual([
      {
        gid: GAP_ONLINE_ITEMS[0].gid,
        token: GAP_ONLINE_ITEMS[0].token,
        title: GAP_ONLINE_ITEMS[0].title,
      },
      {
        gid: GAP_ONLINE_ITEMS[1].gid,
        token: GAP_ONLINE_ITEMS[1].token,
        title: GAP_ONLINE_ITEMS[1].title,
      },
    ]);
  await expect(cards.nth(0)).toContainText("排队中");

  await page.getByTestId("online-batch-favorite").click();
  const dialog = page.getByTestId("online-batch-favorite-dialog");
  await expect(dialog).toBeVisible();
  await dialog.locator("select").selectOption("2");
  await page.getByTestId("online-batch-favorite-confirm").click();

  await expect
    .poll(() => state.favoriteAdds.at(-1)?.items.map((item) => item.gid))
    .toEqual([GAP_ONLINE_ITEMS[0].gid, GAP_ONLINE_ITEMS[1].gid]);
  // Only the gid confirmed by the cloud flips the favourite action.
  await expect(cards.nth(0).getByTestId("fav-button")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(cards.nth(1).getByTestId("fav-button")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("favourite folder page checks only the current folder @gaps2", async ({ page }) => {
  const state = await installGapsMock(page);
  await page.goto("/#/favorites/3");
  await expect(page.getByTestId("favlist-grid")).toBeVisible();

  await page.getByTestId("favlist-check").click();
  await expect.poll(() => state.favoriteChecks).toEqual([3]);
});

test("reader slideshow extends animated pages to the probed duration @gaps2", async ({
  page,
}) => {
  await installGapsMock(page);
  const imageBase = readerPagePath(GAP_READER_GALLERY_ID, 0).replace(/\/0$/, "");
  const metaPath = readerPageMetaEp.path
    .replace("{id}", String(GAP_READER_GALLERY_ID))
    .replace("{id}", "0");
  const metaHits: string[] = [];

  await page.route(new RegExp(`${imageBase}/\\d+$`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600"><rect width="400" height="600" fill="#eee"/></svg>`,
    });
  });
  await page.route(`**${metaPath}`, async (route) => {
    metaHits.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ animated: true, duration_ms: 3000 }),
    });
  });

  await page.goto(`/#/reader/${GAP_READER_GALLERY_ID}/0?slideshow=1`);
  const shell = page.getByTestId("reader-shell");
  await expect(shell).toBeVisible();
  await expect(shell).toHaveAttribute("data-total", "2");
  await expect.poll(() => metaHits.length).toBe(1);
  await expect
    .poll(async () => Number(await shell.getAttribute("data-slide-delay")))
    .toBe(3150);
});
