import { annotateUnverified, expect, test } from "./support";

/**
 * Maintenance views (V-14 … V-19).
 *
 * These pages act on shared recovery/duplicate data. The gate verifies that
 * every list, filter, confirmation and action surface is wired; the actual
 * resolve / ignore / purge / redownload operations are left to an operator
 * because they cannot be limited to test-owned rows.
 */

test("V-14 收藏查重：状态 / 扫描 / 忽略 / 移除入口 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/favorites/manage");
  await expect(page.getByTestId("dupfav-view")).toBeVisible();
  await expect(page.getByTestId("dupfav-scan")).toBeVisible();
  // The `all/local/cloud` filter is one SegmentedControl; each option is a
  // radio button tagged with `data-segmented-value`.
  const filterControl = page.getByTestId("dupfav-filter");
  for (const value of ["all", "local", "cloud"]) {
    await expect(filterControl.locator(`[data-segmented-value="${value}"]`)).toBeVisible();
  }
  await expect(filterControl.locator('[data-segmented-value="all"]')).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await filterControl.locator('[data-segmented-value="local"]').click();
  await expect(page).toHaveURL(/filter=local/);
  await filterControl.locator('[data-segmented-value="all"]').click();
  await expect(page).not.toHaveURL(/filter=local/);
  // `dupfav-summary` renders in every state, so it cannot join an `.or()` with
  // the empty state (that would make two locators match and break strict mode).
  await expect(page.getByTestId("dupfav-summary")).toBeVisible({ timeout: 20_000 });

  // Batch actions only exist while something is selected (SelectionBar).
  const firstRow = page.locator('[data-testid^="dupfav-select-"] input').first();
  if (await firstRow.isVisible().catch(() => false)) {
    await firstRow.check();
    await expect(page.getByTestId("dupfav-selection")).toBeVisible();
    await expect(page.getByTestId("dupfav-unfav")).toBeVisible();
    await expect(page.getByTestId("dupfav-unfav-delete")).toBeVisible();
    await expect(page.getByTestId("dupfav-ignore")).toBeVisible();
    await page.getByTestId("gv-selection-clear").click();
  } else {
    await expect(page.getByTestId("dupfav-empty")).toBeVisible();
    annotateUnverified("favourite duplicates are empty; SelectionBar actions cannot be opened");
  }
  annotateUnverified("duplicate scan / ignore / remove were not executed (shared favourite rows)");
  await app.shot("V-14");
});

test("V-15 重复组与跨 gid 重复 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/duplicates");
  await expect(page.getByTestId("duplicates-view")).toBeVisible();
  await expect(page.getByTestId("duplicates-scan")).toBeVisible();
  await expect(page.getByTestId("duplicates-refresh")).toBeVisible();
  await page.getByTestId("duplicates-refresh").click();
  // `duplicates-summary` is always rendered; the list/empty branch is separate.
  await expect(page.getByTestId("duplicates-summary")).toBeVisible({ timeout: 20_000 });
  await expect(
    page
      .getByTestId("duplicates-empty")
      .or(page.locator('[data-testid^="duplicates-group-"]').first()),
  ).toHaveCount(1, { timeout: 20_000 });

  await page.goto("/#/duplicates/cross-gid");
  await expect(page.getByTestId("dupxgid-view")).toBeVisible();
  await expect(page.getByTestId("dupxgid-recompute")).toBeVisible();
  await expect(page.getByTestId("dupxgid-refresh")).toBeVisible();
  await page.getByTestId("dupxgid-refresh").click();
  // In the empty state `dupxgid-summary` ("0 groups · 0 items") and
  // `dupxgid-hint` ("cross-GID never computed…") are both visible, so the old
  // `.or()` chain matched two nodes and tripped strict mode. Assert the always
  // rendered summary on its own, then require exactly one body branch: hint,
  // empty result, or group cards.
  await expect(page.getByTestId("dupxgid-summary")).toBeVisible({ timeout: 20_000 });
  await expect(
    page
      .getByTestId("dupxgid-hint")
      .or(page.getByTestId("dupxgid-empty"))
      .or(page.locator('[data-testid^="dupxgid-group-"]').first()),
  ).toHaveCount(1, { timeout: 20_000 });
  annotateUnverified("duplicate resolve / keep / dismiss / cross-gid recompute were not executed");
  await app.shot("V-15");
});

test("V-16 更新与忽略列表 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/updates");
  await expect(page.getByTestId("updates-view")).toBeVisible();
  await expect(page.getByTestId("updates-status")).toBeVisible();
  for (const state of ["active", "pending", "downloading", "failed", "all"]) {
    await expect(
      page.getByTestId("updates-state-filter").locator(`[data-segmented-value="${state}"]`),
    ).toBeVisible();
  }
  await expect(page.getByTestId("updates-scan")).toBeVisible();
  // Bulk actions live in the selection bar and appear only with a selection.
  await expect(page.getByTestId("updates-selection")).toHaveCount(0);
  const firstRow = page.locator('[data-testid^="updates-row-"]').first();
  await expect(
    page.getByTestId("updates-empty").or(firstRow),
  ).toBeVisible({ timeout: 20_000 });
  if (await firstRow.isVisible().catch(() => false)) {
    await page.locator('[data-testid^="updates-select-"]').first().check();
    await expect(page.getByTestId("updates-selection")).toBeVisible();
    for (const action of ["updates-update", "updates-update-original", "updates-archive", "updates-ignore"]) {
      await expect(page.getByTestId(action)).toBeVisible();
    }
  } else {
    await expect(page.getByTestId("updates-empty")).toBeVisible();
    annotateUnverified("update list is empty; bulk actions stay hidden until a row is selected");
  }
  await page
    .getByTestId("updates-state-filter")
    .locator('[data-segmented-value="failed"]')
    .click();
  const failedRow = page.locator('[data-testid^="updates-row-"]').first();
  if (await failedRow.isVisible().catch(() => false)) {
    await page.locator('[data-testid^="updates-select-"]').first().check();
    await expect(page.getByTestId("updates-delete")).toBeVisible();
  } else {
    await expect(page.getByTestId("updates-empty")).toBeVisible();
  }

  await page.goto("/#/updates/ignored");
  await expect(page.getByTestId("updates-ignored-view")).toBeVisible();
  await expect(page.getByTestId("updates-unignore-selected")).toBeVisible();
  annotateUnverified("update scan / update / ignore / delete / unignore were not executed (EH budget)");
  await app.shot("V-16");
});

test("V-17 回收站与已清除列表 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/recycle");
  await expect(page.getByTestId("recycle-view")).toBeVisible();
  const empty = page.getByTestId("recycle-empty");
  const firstItem = page.locator('[data-testid^="recycle-item-"]').first();
  await expect(empty.or(firstItem)).toBeVisible({ timeout: 20_000 });

  // Bulk actions only exist while something is selected (RC-03): the empty
  // selection has no disabled restore / purge shells.
  await expect(page.getByTestId("recycle-restore")).toHaveCount(0);
  await expect(page.getByTestId("recycle-purge")).toHaveCount(0);

  if (await firstItem.isVisible().catch(() => false)) {
    await firstItem.locator('input[type="checkbox"]').first().check();
    const purge = page.getByTestId("recycle-purge");
    await expect(page.getByTestId("recycle-restore")).toBeVisible();
    await expect(purge).toBeVisible();
    await purge.click();
    await expect(page.getByTestId("recycle-purge-dialog")).toBeVisible();
    await expect(page.getByTestId("recycle-delete-files")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("recycle-purge-dialog")).toHaveCount(0);
  } else {
    await expect(empty).toBeVisible();
    annotateUnverified("recycle bin is empty; purge needs a selection (bulk bar hidden by design)");
  }

  await page
    .getByTestId("recycle-tabs")
    .locator('[data-segmented-value="expunged"]')
    .click();
  const firstExpunged = page.locator('[data-testid^="recycle-item-"]').first();
  await expect(empty.or(firstExpunged)).toBeVisible({ timeout: 20_000 });
  // Switching tabs clears the selection.
  await expect(page.getByTestId("recycle-redownload")).toHaveCount(0);
  if (await firstExpunged.isVisible().catch(() => false)) {
    await firstExpunged.locator('input[type="checkbox"]').first().check();
    await expect(page.getByTestId("recycle-redownload")).toBeVisible();
  } else {
    annotateUnverified("expunged list is empty; redownload needs a selection");
  }

  await page
    .getByTestId("recycle-tabs")
    .locator('[data-segmented-value="trash"]')
    .click();
  annotateUnverified("restore / purge / redownload were not confirmed (shared recycle bin)");
  await app.shot("V-17");
});

test("V-18 完整性检查列表 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/integrity");
  await expect(page.getByTestId("integrity-view")).toBeVisible();
  await expect(page.getByTestId("integrity-scan")).toBeVisible();
  await expect(page.getByTestId("integrity-select-all")).toBeVisible();
  await expect(
    page.getByTestId("integrity-empty").or(page.getByTestId("integrity-summary")),
  ).toBeVisible({ timeout: 20_000 });
  annotateUnverified("integrity scan / repair / redownload were not executed (long-running)");
  await app.shot("V-18");
});

test("V-19 归档列表与发起 / 取消 / 清理入口 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/archive");
  await expect(page.getByTestId("archive-page")).toBeVisible();
  await expect(page.getByTestId("archive-status")).toBeVisible();
  await expect(page.getByTestId("archive-start")).toBeVisible();
  await expect(page.getByTestId("archive-cancel")).toBeVisible();
  await page.getByTestId("archive-purge").click();
  await expect(page.getByTestId("archive-purge-confirm")).toBeVisible();
  await page.keyboard.press("Escape");
  annotateUnverified("archive start / cancel / purge were not executed (server-side archive job)");
  await app.shot("V-19");
});
