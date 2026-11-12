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
  for (const filter of ["all", "local", "cloud"]) {
    await expect(page.getByTestId(`dupfav-filter-${filter}`)).toBeVisible();
  }
  await expect(
    page.getByTestId("dupfav-empty").or(page.getByTestId("dupfav-summary")),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("dupfav-unfav")).toBeVisible();
  await expect(page.getByTestId("dupfav-unfav-delete")).toBeVisible();
  await expect(page.getByTestId("dupfav-ignore")).toBeVisible();
  annotateUnverified("favourite-duplicate scan / ignore / remove were not executed (shared favourite rows)");
  await app.shot("V-14");
});

test("V-15 重复组与跨 gid 重复 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/duplicates");
  await expect(page.getByTestId("duplicates-view")).toBeVisible();
  await expect(page.getByTestId("duplicates-scan")).toBeVisible();
  await expect(page.getByTestId("duplicates-refresh")).toBeVisible();
  await page.getByTestId("duplicates-refresh").click();
  await expect(
    page.getByTestId("duplicates-empty").or(page.getByTestId("duplicates-summary")),
  ).toBeVisible({ timeout: 20_000 });

  await page.goto("/#/duplicates/cross-gid");
  await expect(page.getByTestId("dupxgid-view")).toBeVisible();
  await expect(page.getByTestId("dupxgid-recompute")).toBeVisible();
  await expect(page.getByTestId("dupxgid-refresh")).toBeVisible();
  await page.getByTestId("dupxgid-refresh").click();
  await expect(
    page
      .getByTestId("dupxgid-empty")
      .or(page.getByTestId("dupxgid-hint"))
      .or(page.getByTestId("dupxgid-summary")),
  ).toBeVisible({ timeout: 20_000 });
  annotateUnverified("duplicate resolve / keep / dismiss / cross-gid recompute were not executed");
  await app.shot("V-15");
});

test("V-16 更新与忽略列表 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/updates");
  await expect(page.getByTestId("updates-view")).toBeVisible();
  await expect(page.getByTestId("updates-status")).toBeVisible();
  for (const state of ["active", "pending", "downloading", "failed", "all"]) {
    await expect(page.getByTestId(`updates-state-${state}`)).toBeVisible();
  }
  for (const action of ["updates-scan", "updates-update", "updates-update-original", "updates-archive", "updates-ignore"]) {
    await expect(page.getByTestId(action)).toBeVisible();
  }
  await page.getByTestId("updates-state-failed").click();
  await expect(page.getByTestId("updates-delete")).toBeVisible();
  await expect(
    page.getByTestId("updates-empty").or(page.locator('[data-testid^="updates-row-"]').first()),
  ).toBeVisible({ timeout: 20_000 });

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
  await expect(page.getByTestId("recycle-restore")).toBeVisible();
  const purge = page.getByTestId("recycle-purge");
  await expect(purge).toBeVisible();

  // Purge requires a selection; on an empty bin the control is disabled by
  // design. Only open the dialog when a recycle-bin row exists to select.
  if (await firstItem.isVisible().catch(() => false)) {
    await page.locator('[data-testid^="recycle-select-"]').first().check();
    await expect(purge).toBeEnabled();
    await purge.click();
    await expect(page.getByTestId("recycle-purge-dialog")).toBeVisible();
    await expect(page.getByTestId("recycle-delete-files")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("recycle-purge-dialog")).toHaveCount(0);
  } else {
    await expect(empty).toBeVisible();
    await expect(purge).toBeDisabled();
    annotateUnverified("recycle bin is empty; purge cannot be opened without a selection (disabled by design)");
  }

  await page.getByTestId("recycle-tab-expunged").click();
  await expect(page.getByTestId("recycle-redownload")).toBeVisible();
  // Switching tabs clears the selection, so purge is disabled again unless an
  // expunged row can be selected.
  const firstExpunged = page.locator('[data-testid^="recycle-item-"]').first();
  await expect(empty.or(firstExpunged)).toBeVisible({ timeout: 20_000 });
  await expect(purge).toBeDisabled();
  if (await firstExpunged.isVisible().catch(() => false)) {
    await page.locator('[data-testid^="recycle-select-"]').first().check();
    await expect(purge).toBeEnabled();
  } else {
    annotateUnverified("expunged list is empty; purge stays disabled without a selection");
  }

  await page.getByTestId("recycle-tab-trash").click();
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
