import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures/mock";
import { installLibraryMock } from "./fixtures/library/seed";
import { installLibManageMock } from "./fixtures/lib-manage/mock";

const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true });
});

function watchConsole(page: import("@playwright/test").Page): string[] {
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

async function libraryGrid(page: import("@playwright/test").Page) {
  const grid = page.getByTestId("library-grid");
  await expect(grid).toBeVisible();
  return grid;
}

test("library batch delete asks for confirmation twice and calls delete-bulk @lib-manage", async ({
  page,
}) => {
  const csp = watchConsole(page);
  await installLibraryMock(page, { total: 12 });
  const state = await installLibManageMock(page);

  await page.goto("/#/library");
  await libraryGrid(page);
  await expect(page.getByTestId("library-manage")).toBeVisible();

  const cards = page.getByTestId("library-card");
  await cards.nth(0).locator('input[type="checkbox"]').check();
  await cards.nth(1).locator('input[type="checkbox"]').check();
  await expect(page.getByTestId("selection-count")).toContainText("2");

  await page.getByTestId("batch-delete").click();
  const dialog = page.getByTestId("batch-delete-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("删除所选条目");

  await page.getByTestId("batch-delete-confirm").click();
  await expect(dialog).toContainText("再次确认");
  expect(state.deletedBulk).toHaveLength(0);

  await page.getByTestId("batch-delete-confirm").click();
  await expect.poll(() => state.deletedBulk.length).toBe(1);
  expect(state.deletedBulk[0]?.ids).toEqual([1, 2]);
  expect(state.deletedBulk[0]?.delete_files).toBe(false);
  await expect(page.getByTestId("selection-count")).toContainText("0");
  expect(csp).toEqual([]);
});

test("filtered delete requires typing the match count above the threshold @lib-manage", async ({
  page,
}) => {
  const csp = watchConsole(page);
  await installLibraryMock(page, { total: 12 });
  const state = await installLibManageMock(page);

  await page.goto("/#/library?q=dragon");
  await libraryGrid(page);

  await page.getByTestId("filtered-delete").click();
  const dialog = page.getByTestId("filtered-delete-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("q: dragon");

  await page.getByTestId("filtered-delete-confirm").click();
  await expect.poll(() => state.deleteFilteredCalls).toBe(1);
  const countInput = page.getByTestId("filtered-delete-count");
  await expect(countInput).toBeVisible();
  await expect(dialog).toContainText("250");

  const confirm = page.getByTestId("filtered-delete-confirm");
  await countInput.locator("input").fill("1");
  await expect(confirm).toBeDisabled();
  await countInput.locator("input").fill("250");
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await expect.poll(() => state.deleteFilteredCalls).toBe(2);
  const last = state.deletedFiltered.at(-1) ?? {};
  expect(last.confirm).toBe(true);
  expect(last.match_count).toBe(250);
  expect(last.q).toBe("dragon");
  expect(csp).toEqual([]);
});

test("library saved searches, new list and add-to-list call the API @lib-manage", async ({
  page,
}) => {
  const csp = watchConsole(page);
  await installLibraryMock(page, { total: 12 });
  const state = await installLibManageMock(page);

  await page.goto("/#/library");
  await libraryGrid(page);

  const savedSelect = page.getByTestId("saved-search-select").locator("select");
  await expect(savedSelect.locator("option")).toHaveCount(2);
  await savedSelect.selectOption("saved-1");
  await page.getByTestId("apply-search").click();
  await expect(page).toHaveURL(/tags=language(?::|%3A)chinese/);

  await page.getByTestId("save-search-open").click();
  await page.getByTestId("save-search-name").locator("input").fill("我的搜索");
  await page.getByTestId("save-search-submit").click();
  await expect.poll(() => state.savedSearches.length).toBe(2);
  expect(state.savedSearches[1]?.name).toBe("我的搜索");
  expect(state.savedSearches[1]?.query.tags).toBe("language:chinese");

  await page.getByTestId("new-list").click();
  await page.getByTestId("new-list-name").locator("input").fill("夜间清单");
  await page.getByTestId("new-list-submit").click();
  await expect.poll(() => state.lists.some((item) => item.name === "夜间清单")).toBe(true);

  await page.getByTestId("library-card").nth(0).locator('input[type="checkbox"]').check();
  await page.getByTestId("add-to-list").click();
  const addDialog = page.getByTestId("add-list-dialog");
  await expect(addDialog).toBeVisible();
  await addDialog.locator("select").first().selectOption("1");
  await page.getByTestId("add-list-submit").click();
  await expect.poll(() => state.lists[0]?.count).toBe(4);
  expect(csp).toEqual([]);
});

test("series selection survives paging and batch download uses both sources @lib-manage", async ({
  page,
}) => {
  const csp = watchConsole(page);
  await page.addInitScript(() => localStorage.setItem("gv_page_size", "2"));
  const state = await installLibManageMock(page);

  await page.goto("/#/series");
  await expect(page.getByTestId("series-view")).toBeVisible();
  await expect(page.getByTestId("series-page-info")).toContainText("1 / 2");

  const firstPageGroups = page.getByTestId("series-group");
  await expect(firstPageGroups).toHaveCount(2);

  const alphaMembers = firstPageGroups.nth(0).getByTestId("series-member");
  const betaMembers = firstPageGroups.nth(1).getByTestId("series-member");
  await alphaMembers.nth(0).locator('input[type="checkbox"]').check();
  await alphaMembers.nth(1).locator('input[type="checkbox"]').check();
  await betaMembers.nth(0).locator('input[type="checkbox"]').check();
  await expect(page.getByTestId("series-selection")).toContainText("3");

  await page.getByTestId("series-next").click();
  await expect(page.getByTestId("series-page-info")).toContainText("2 / 2");
  const gammaMembers = page.getByTestId("series-group").nth(0).getByTestId("series-member");
  await gammaMembers.nth(1).locator('input[type="checkbox"]').check();
  await expect(page.getByTestId("series-selection")).toContainText("4");

  await page.getByTestId("series-prev").click();
  await expect(page.getByTestId("series-page-info")).toContainText("1 / 2");
  const alphaAgain = page.getByTestId("series-group").nth(0).getByTestId("series-member");
  await expect(alphaAgain.nth(0).locator('input[type="checkbox"]')).toBeChecked();
  await expect(alphaAgain.nth(1).locator('input[type="checkbox"]')).toBeChecked();
  await expect(page.getByTestId("series-selection")).toContainText("4");

  await page.getByTestId("series-download").click();
  await expect.poll(() => state.redownloads.length).toBe(2);
  expect(state.redownloads.sort()).toEqual([11, 12]);
  await expect.poll(() => state.favoriteDownloads.length).toBe(1);
  expect(state.favoriteDownloads[0]?.favcat).toBe(3);
  expect(state.favoriteDownloads[0]?.gids.sort()).toEqual([200011, 200013]);
  expect(csp).toEqual([]);
});

test("series create, rename, rebuild, add candidates, remove and delete @lib-manage", async ({
  page,
}) => {
  const csp = watchConsole(page);
  const state = await installLibManageMock(page);

  await page.goto("/#/series");
  await expect(page.getByTestId("series-group")).toHaveCount(3);

  await page.getByTestId("series-create").click();
  await page.getByTestId("series-name-input").locator("input").fill("新系列");
  await page.getByTestId("series-name-submit").click();
  await expect.poll(() => state.seriesCreates).toEqual(["新系列"]);

  const alpha = page.getByTestId("series-group").filter({ hasText: "Alpha Collection" });
  await alpha.getByTestId("series-rename").click();
  await page.getByTestId("series-name-input").locator("input").fill("Alpha Renamed");
  await page.getByTestId("series-name-submit").click();
  await expect.poll(() => state.seriesRenames.length).toBe(1);
  expect(state.seriesRenames[0]).toEqual({ id: 41, name: "Alpha Renamed" });

  await page.getByTestId("series-rebuild").click();
  await expect.poll(() => state.seriesRebuilds).toBe(1);

  await alpha.getByTestId("series-add-item").click();
  const addDialog = page.getByTestId("series-add-dialog");
  await expect(addDialog).toBeVisible();
  const candidates = addDialog.locator(".candidate");
  await expect(candidates).toHaveCount(2);
  await candidates.first().locator('input[type="checkbox"]').check();
  await addDialog.getByTestId("series-add-submit").click();
  await expect.poll(() => state.cloudItemsAdded.length).toBe(1);
  expect(state.cloudItemsAdded[0]).toEqual({ id: 41, gids: [300001] });

  await alpha.getByTestId("series-remove-item").click();
  const removeDialog = page.getByTestId("series-remove-manual-dialog");
  await expect(removeDialog).toBeVisible();
  await removeDialog.getByTestId("series-remove-gids").locator("input").fill("200011");
  await removeDialog.getByTestId("series-remove-submit").click();
  await expect.poll(() => state.cloudItemsRemoved.length).toBe(1);
  expect(state.cloudItemsRemoved[0]).toEqual({ id: 41, gids: [200011] });

  await alpha.getByTestId("series-delete").click();
  await page.getByTestId("series-delete-confirm").click();
  await expect.poll(() => state.seriesDeletes).toEqual([41]);
  expect(csp).toEqual([]);
});

test("tags search, namespace filter, reload and tag sync @lib-manage", async ({ page }) => {
  const csp = watchConsole(page);
  const state = await installLibManageMock(page);

  await page.goto("/#/tags");
  await expect(page.getByTestId("tags-view")).toBeVisible();
  await expect(page.getByTestId("tags-cloud")).toBeVisible();
  await expect(page.getByTestId("tags-ns-artist")).toContainText("80");

  await page.getByTestId("tags-ns-artist").click();
  await expect(page).toHaveURL(/ns=artist/);
  await expect(page.getByTestId("tags-current-ns")).toContainText("artist");
  await expect(page.getByTestId("tags-cloud").locator("[data-namespace]")).toHaveCount(2);

  await page.getByTestId("tags-search-input").locator("input").fill("dragon");
  await page.getByTestId("tags-search-submit").click();
  await expect(page).toHaveURL(/q=dragon/);
  await expect
    .poll(() => state.tagQueries.at(-1)?.get("q"), { timeout: 10_000 })
    .toBe("dragon");

  await page.getByTestId("tags-reload").click();
  await expect.poll(() => state.tagReloads).toBe(1);

  await page.getByTestId("tags-sync").click();
  await expect.poll(() => state.tagSyncStarts).toBe(1);
  expect(csp).toEqual([]);
});

test("gallery manage section edits local fields, notes, lists and deletes @lib-manage", async ({
  page,
}) => {
  const csp = watchConsole(page);
  const state = await installLibManageMock(page);

  await page.goto("/#/gallery/5");
  await expect(page.getByTestId("gallery-detail")).toBeVisible();
  const manage = page.getByTestId("gallery-manage");
  await expect(manage).toBeVisible();
  await expect(manage.getByTestId("gallery-lists")).toBeVisible();

  await page.getByTestId("local-tags").locator("input").fill("favourite, custom");
  await page.getByTestId("local-note").fill("新的本地备注");
  await page.getByTestId("save-local").click();
  await expect.poll(() => state.localPatches.length).toBe(1);
  expect(state.localPatches[0]?.local_note).toBe("新的本地备注");
  expect(state.localPatches[0]?.local_tags).toEqual(["favourite", "custom"]);

  await page.getByTestId("list-toggle-2").click();
  await expect.poll(() => state.lists[1]?.count).toBe(2);

  const noteInput = page.getByTestId("fav-note").locator("input");
  await expect(noteInput).toHaveValue("cloud note");
  await noteInput.fill("云端备注");
  await page.getByTestId("save-fav-note").click();
  await expect.poll(() => state.favoriteNotes.length).toBe(1);
  expect(state.favoriteNotes[0]?.gid).toBe(200005);
  expect(state.favoriteNotes[0]?.favcat).toBe(1);
  expect(state.favoriteNotes[0]?.note).toBe("云端备注");

  await page.getByTestId("sync-tags").click();
  await expect.poll(() => state.syncTags).toBe(1);

  await page.getByTestId("redownload").click();
  await expect.poll(() => state.redownloads).toEqual([5]);

  await page.getByTestId("download-original").click();
  await expect.poll(() => state.originalDownloads.length).toBe(1);
  expect(state.originalDownloads[0]).toEqual({ id: 5, archive: false });

  await page.getByTestId("delete-gallery").click();
  await expect(page.getByTestId("delete-gallery-dialog")).toBeVisible();
  await page.getByTestId("delete-gallery-confirm").click();
  await expect.poll(() => state.galleryDeletes.length).toBe(1);
  expect(state.galleryDeletes[0]).toEqual({ id: 5, delete_files: "false" });
  await expect(page).toHaveURL(/#\/library/);
  expect(csp).toEqual([]);
});

test("screenshots cover library manage, series, tags and gallery manage @lib-manage", async ({
  page,
}) => {
  await installLibraryMock(page, { total: 24 });
  await installLibManageMock(page);

  const themes = ["dark", "light"] as const;
  const viewports = [
    { width: 1280, height: 900, label: "1280" },
    { width: 390, height: 844, label: "390" },
  ];

  for (const theme of themes) {
    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto("/#/library");
      await page.evaluate((value) => localStorage.setItem("gv_theme", value), theme);
      await page.reload();
      await libraryGrid(page);
      await expect(page.getByTestId("library-manage")).toBeVisible();
      await page.getByTestId("library-card").nth(0).locator('input[type="checkbox"]').check();
      await page.screenshot({
        path: join(SHOTS, `library-manage-${theme}-${viewport.label}.png`),
      });

      await page.goto("/#/series");
      await expect(page.getByTestId("series-group").first()).toBeVisible();
      await page.screenshot({
        path: join(SHOTS, `series-${theme}-${viewport.label}.png`),
      });

      await page.goto("/#/tags");
      await expect(page.getByTestId("tags-cloud")).toBeVisible();
      await page.screenshot({
        path: join(SHOTS, `tags-${theme}-${viewport.label}.png`),
      });

      await page.goto("/#/gallery/5");
      await expect(page.getByTestId("gallery-manage")).toBeVisible();
      await page.screenshot({
        path: join(SHOTS, `gallery-manage-${theme}-${viewport.label}.png`),
        fullPage: true,
      });
    }
  }
});
