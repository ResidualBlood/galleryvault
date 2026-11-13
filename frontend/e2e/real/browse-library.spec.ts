/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import { annotateUnverified, expect, test, uniqueName } from "./support";

/**
 * Local browse / library / series / tags parity (V-01, V-02, V-06, V-07).
 *
 * Saved searches and lists are created through the UI and removed afterwards;
 * deleting existing galleries is intentionally not automated because the test
 * library is shared and not owned by this suite.
 */
test("V-01 最近入库 / 继续阅读 / 标签概览 / 随机 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/browse");
  await expect(page.getByTestId("browse-view")).toBeVisible();
  await expect(page.getByTestId("browse-tag-overview")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("random-button")).toBeVisible();

  const history = page.getByTestId("continue-reading");
  const historyVisible = await history.isVisible().catch(() => false);
  if (historyVisible) {
    await expect(history.getByTestId(/^continue-/).first()).toBeVisible();
  } else {
    annotateUnverified("no reading history; continue-reading section was not rendered");
  }

  const grid = page.getByTestId("browse-grid");
  const empty = page.getByTestId("browse-empty");
  await expect(grid.or(empty)).toBeVisible({ timeout: 20_000 });
  await app.shot("V-01");
});

test("V-02 库搜索 / 筛选 / 排序 / 分页 / 保存搜索 / 清单 @parity", async ({ app }) => {
  const { page } = app;
  const name = uniqueName("parity-search");
  const listName = uniqueName("parity-list");
  let listId: number | null = null;
  let savedSearchCreated = false;

  try {
    const existing = await app.api.get<{ items: Array<{ id: string }> }>("/api/saved-searches");
    test.skip(
      (existing.items?.length ?? 0) >= 20,
      "saved-search limit reached; create/delete would be rejected by the backend",
    );

    await page.goto("/#/library");
    await expect(page.getByTestId("library-view")).toBeVisible();

    // Infinite-scroll grid / page-size / sort controls. Page size lives in the
    // collapsible filter panel, so open it first.
    await page.getByTestId("advanced-toggle").click();
    await expect(page.getByTestId("advanced-filters")).toBeVisible();
    await page.locator('[data-testid="page-size-select"] select').selectOption("100");
    await expect(page).toHaveURL(/page_size=100/);
    await page.locator('[data-testid="order-select"] select').selectOption("title_asc");
    await expect(page).toHaveURL(/order_by=title_asc/);
    const grid = page.getByTestId("library-grid");
    const empty = page.getByTestId("library-empty");
    await expect(grid.or(empty)).toBeVisible({ timeout: 20_000 });
    if (await grid.isVisible().catch(() => false)) {
      await expect(page.getByTestId("grid-sentinel")).toBeVisible();
    }

    // Saved search: create through the dialog, then delete through the toolbar.
    await page.getByTestId("save-search-open").click();
    await page.locator('[data-testid="save-search-name"] input').fill(name);
    await page.getByTestId("save-search-submit").click();
    await expect(page.getByTestId("save-search-name")).toHaveCount(0);
    savedSearchCreated = true;
    const savedSelect = page.locator('[data-testid="saved-search-select"] select');
    await savedSelect.selectOption({ label: name });
    await page.getByTestId("delete-search").click();
    await expect(savedSelect.locator("option", { hasText: name })).toHaveCount(0);
    savedSearchCreated = false;

    // List: create through the dialog, add a selected gallery, remove the list
    // via the API in `finally` (the legacy UI has no list-delete button).
    await page.getByTestId("new-list").click();
    await page.locator('[data-testid="new-list-name"] input').fill(listName);
    await page.getByTestId("new-list-submit").click();
    await expect(page.getByTestId("new-list-name")).toHaveCount(0);
    const lists = await app.api.get<{ items: Array<{ id: number; name: string }> }>("/api/lists");
    listId = lists.items.find((item) => item.name === listName)?.id ?? null;
    expect(listId).not.toBeNull();

    const cards = page.getByTestId("library-card");
    const cardCount = await cards.count();
    if (cardCount > 0 && listId !== null) {
      await cards.first().locator('input[type="checkbox"]').check({ force: true });
      await page.getByTestId("add-to-list").click();
      await expect(page.getByTestId("add-list-dialog")).toBeVisible();
      const dialog = page.getByTestId("add-list-dialog");
      await dialog.locator("select").first().selectOption(String(listId));
      await page.getByTestId("add-list-submit").click();
      await expect(page.getByTestId("add-list-dialog")).toHaveCount(0);
    } else {
      annotateUnverified("library is empty; add-to-list was not exercised");
    }

    // Destructive dialogs: confirm they exist and close without confirming.
    if (cardCount > 0) {
      await cards.first().locator('input[type="checkbox"]').check({ force: true });
      await page.getByTestId("batch-delete").click();
      await expect(page.getByTestId("batch-delete-confirm")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("batch-delete-dialog")).toHaveCount(0);

      await cards.first().locator('input[type="checkbox"]').check({ force: true });
      await page.getByTestId("batch-favorite").click();
      await expect(page.getByTestId("batch-favorite-target")).toBeVisible();
      await page.keyboard.press("Escape");
      annotateUnverified("batch favourite cloud write was cancelled at the picker");
    } else {
      annotateUnverified("library is empty; batch delete / batch favourite were not exercised");
    }

    await page.goto("/#/library?q=a");
    await expect(page.getByTestId("library-view")).toBeVisible();
    await page.getByTestId("advanced-toggle").click();
    await expect(page.getByTestId("advanced-filters")).toBeVisible();
    await page.getByTestId("filtered-delete").click();
    await expect(page.getByTestId("filtered-delete-confirm")).toBeVisible();
    await page.keyboard.press("Escape");
    annotateUnverified("filtered delete was not confirmed (would delete shared library rows)");
  } finally {
    if (savedSearchCreated) {
      const saved = await app.api
        .get<{ items: Array<{ id: string; name: string }> }>("/api/saved-searches")
        .catch(() => ({ items: [] }));
      const hit = saved.items.find((item) => item.name === name);
      if (hit) await app.api.del(`/api/saved-searches/${encodeURIComponent(hit.id)}`).catch(() => undefined);
    }
    if (listId !== null) {
      await app.api.del(`/api/lists/${listId}`).catch(() => undefined);
    }
  }
  await app.shot("V-02");
});

test("V-06 系列：列表 / 新建 / 改名 / 删除 / 云端候选入口 @parity", async ({ app }) => {
  const { page } = app;
  const name = uniqueName("parity-series");
  const renamed = `${name}-renamed`;
  let seriesId: number | null = null;
  let deleted = false;

  try {
    const created = await app.api.post<{ id: number; name: string }>("/api/series", {
      name,
    });
    seriesId = created.id;
    expect(seriesId).toBeGreaterThan(0);

    // Empty series are hidden unless show_all is on; the newly created group
    // has no members yet, so start from the show-all list.
    await page.goto("/#/series?show_all=1");
    await expect(page.getByTestId("series-view")).toBeVisible();
    const group = page.getByTestId("series-group").filter({ hasText: name }).first();
    await expect(group).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("series-stats")).toBeVisible();

    await group.getByTestId("series-rename").click();
    await page.locator('[data-testid="series-name-input"] input').fill(renamed);
    await page.getByTestId("series-name-submit").click();
    const renamedGroup = page.getByTestId("series-group").filter({ hasText: renamed }).first();
    await expect(renamedGroup).toBeVisible({ timeout: 20_000 });

    await page.getByTestId("series-show-all").click();
    await expect(page).not.toHaveURL(/show_all=1/);
    await page.getByTestId("series-show-all").click();
    await expect(page).toHaveURL(/show_all=1/);
    await expect(renamedGroup).toBeVisible({ timeout: 20_000 });

    await renamedGroup.getByTestId("series-delete").click();
    await page.getByTestId("series-delete-confirm").click();
    await expect(page.getByTestId("series-group").filter({ hasText: renamed })).toHaveCount(0);
    deleted = true;

    annotateUnverified(
      "series cloud candidates, rebuild and download-selected were not executed (EH budget / shared favourites)",
    );
  } finally {
    if (seriesId !== null && !deleted) {
      await app.api.del(`/api/series/${seriesId}`).catch(() => undefined);
    }
  }
  await app.shot("V-06");
});

test("V-07 标签：namespace / 搜索 / 重载 / 同步入口 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/tags");
  await expect(page.getByTestId("tags-view")).toBeVisible();

  await expect(page.getByTestId("tags-reload")).toBeVisible();
  await expect(page.getByTestId("tags-sync")).toBeVisible();
  await page.getByTestId("tags-reload").click();

  await page.locator('[data-testid="tags-search-input"] input').fill("a");
  await page.getByTestId("tags-search-submit").click();
  await expect(
    page.getByTestId("tags-cloud").or(page.getByTestId("tag-empty")),
  ).toBeVisible({ timeout: 20_000 });

  const namespace = page.locator('[data-testid^="tags-ns-"]').nth(1);
  if (await namespace.isVisible().catch(() => false)) {
    await namespace.click();
    await expect(page.getByTestId("tags-current-ns")).toBeVisible();
  } else {
    annotateUnverified("no tag namespace facet was returned");
  }

  annotateUnverified(
    "tag sync start and per-gallery tag sync were not executed (long-running / EH-touching)",
  );
  await app.shot("V-07");
});
