/* eslint-disable no-restricted-syntax -- real parity tests exercise the legacy HTTP surface directly */
import settingsMap from "../../parity/settings-map.json" with { type: "json" };
import { annotateUnverified, expect, screenshot, test } from "./support";

/**
 * Logs / settings / design / API-token parity (V-10, V-11, N-05 … N-07).
 *
 * Password changes and API-token generation are deliberately not executed:
 * the former would lock the shared test account, and the latter would put a
 * live credential into a Playwright trace/screenshot. Their status and control
 * surfaces are still verified.
 */

test("V-10 日志：任务日志 / 系统日志 / 筛选 / 下载 / 清空入口 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/logs");
  await expect(page.getByTestId("logs-page")).toBeVisible();
  await expect(page.getByTestId("logs-activity")).toBeVisible();

  await page.getByTestId("logs-tab-system").click();
  await expect(page.getByTestId("logs-system")).toBeVisible();
  await expect(page.getByTestId("syslog-list")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("syslog-level")).toBeVisible();
  await expect(page.getByTestId("syslog-filter")).toBeVisible();
  await expect(page.getByTestId("syslog-search")).toBeVisible();
  await expect(page.getByTestId("syslog-autoscroll")).toBeVisible();

  const download = await page.request.get("/api/system/logs/download");
  expect(download.ok()).toBeTruthy();

  await page.getByTestId("syslog-clear").click();
  await expect(page.getByTestId("syslog-clear-confirm")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("syslog-clear-confirm")).toHaveCount(0);

  await page.getByTestId("logs-tab-activity").click();
  await expect(page.getByTestId("logs-activity")).toBeVisible();
  const cancel = page.getByTestId("logs-cancel").first();
  if (await cancel.isVisible().catch(() => false)) {
    annotateUnverified("running background task cancel was not clicked");
  } else {
    annotateUnverified("no cancellable background task was running");
  }
  await app.shot("V-10");
});

test("V-11 设置：13 组全部字段 / 存储 / 标签 / 连接与测试入口 @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/settings");
  await expect(page.getByTestId("settings-page")).toBeVisible();
  await expect(page.getByTestId("settings-nav")).toBeVisible();

  const groups = settingsMap.groups;
  await expect(page.locator("[data-settings-nav]")).toHaveCount(groups.length);
  for (const group of groups) {
    await page.locator(`[data-settings-nav="${group.id}"]`).click();
    const section = page.locator(`[data-settings-group="${group.id}"]`);
    await expect(section).toBeVisible();
    await expect(section.locator("[data-setting-key]")).toHaveCount(group.fields.length);
  }

  await page.locator('[data-settings-nav="network"]').click();
  await expect(page.locator('[data-action-id="eh-test"]')).toBeVisible();

  await page.locator('[data-settings-nav="notifications"]').click();
  await expect(page.locator('[data-action-id="test-telegram"]')).toBeVisible();

  await page.locator('[data-settings-nav="library"]').click();
  await expect(page.locator('[data-action-id="gen-thumbs"]')).toBeVisible();
  await expect(page.locator('[data-setting-key="thumbnail_status"]')).toBeVisible();

  await page.locator('[data-settings-nav="tags"]').click();
  await expect(page.locator('[data-action-id="sync-all-tags"]')).toBeVisible();
  await expect(page.locator('[data-action-id="repair-categories"]')).toBeVisible();
  await expect(page.locator('[data-setting-key="translation_status"]')).toBeVisible();

  await page.locator('[data-settings-nav="system"]').click();
  await expect(page.locator('[data-settings-section="storage"]')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("[data-storage-row]")).toHaveCount(4);

  await page.locator('[data-settings-nav="account"]').click();
  await expect(page.locator('[data-settings-section="password"]')).toBeVisible();
  await expect(page.getByTestId("api-token-status")).toBeVisible();
  annotateUnverified(
    "EH connection test / change password / Telegram test / thumbnail generation / tag sync / repair categories were not executed",
  );
  await app.shot("V-11");
});

test("N-05 设置分组：13 组 / 按组保存只提交改动键 / 敏感确认 / 凭据不回显 @parity", async ({ app }) => {
  const { page } = app;
  const current = await app.api.get<Record<string, unknown>>("/api/settings");
  const originalTitle = String(current.title_display ?? "japanese");
  const nextTitle = originalTitle === "english" ? "japanese" : "english";

  try {
    await page.goto("/#/settings");
    const groups = settingsMap.groups;
    await expect(page.getByTestId("settings-nav")).toBeVisible();
    await expect(page.locator("[data-settings-nav]")).toHaveCount(groups.length);

    await page.locator('[data-testid="settings-search"] input').fill("cookie");
    await expect(
      page.getByTestId("settings-search-results").or(page.getByTestId("settings-search-empty")),
    ).toBeVisible();
    await page.locator('[data-testid="settings-search"] input').fill("");

    await page.locator('[data-settings-nav="appearance"]').click();
    const title = page.locator('[data-setting-key="title_display"] select');
    await title.selectOption(nextTitle);
    await expect(page.getByTestId("settings-save")).toBeVisible();

    const posted = page.waitForRequest(
      (request) =>
        request.method() === "POST" && request.url().endsWith("/api/settings"),
    );
    const response = page.waitForResponse(
      (res) => res.request().method() === "POST" && res.url().endsWith("/api/settings"),
    );
    await page.getByTestId("settings-save").click();
    const payload = (await posted).postDataJSON() as Record<string, unknown>;
    expect(Object.keys(payload)).toEqual(["title_display"]);
    expect(payload.title_display).toBe(nextTitle);
    expect((await response).ok()).toBeTruthy();

    // Security-sensitive key: open the password confirmation, then cancel.
    await page.reload();
    await expect(page.getByTestId("settings-page")).toBeVisible();
    await page.locator('[data-settings-nav="account"]').click();
    await page.locator('[data-setting-key="auth_required"] button[role="switch"]').click();
    await page.getByTestId("settings-save").click();
    await expect(page.getByTestId("security-confirm")).toBeVisible();
    await expect(page.locator('[data-testid="security-password"] input')).toHaveAttribute("type", "password");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("security-confirm")).toHaveCount(0);

    // Secrets are write-only inputs: never echoed back into the DOM.
    await page.reload();
    await page.locator('[data-settings-nav="network"]').click();
    const secrets = page.locator('[data-secret-input="true"] input');
    const count = await secrets.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(secrets.nth(index)).toHaveValue("");
      await expect(secrets.nth(index)).toHaveAttribute("type", "password");
    }
  } finally {
    await app.api.post("/api/settings", { title_display: originalTitle }).catch(() => undefined);
  }
  await app.shot("N-05");
});

test("N-06 设计一致性：亮 / 暗 × 桌面 / 手机截图与溢出检查 @parity", async ({ app }) => {
  const { page } = app;
  const original = await page.evaluate(() => ({
    theme: localStorage.getItem("gv_theme"),
    width: window.innerWidth,
  }));

  try {
    const pages = ["/#/library", "/#/settings"];
    const variants = [
      { theme: "light", width: 1280, height: 900, name: "light-desktop" },
      { theme: "dark", width: 1280, height: 900, name: "dark-desktop" },
      { theme: "light", width: 390, height: 844, name: "light-mobile" },
      { theme: "dark", width: 390, height: 844, name: "dark-mobile" },
    ];
    for (const variant of variants) {
      await page.setViewportSize({ width: variant.width, height: variant.height });
      await page.evaluate((theme) => localStorage.setItem("gv_theme", theme), variant.theme);
      for (const path of pages) {
        await page.goto(path);
        await expect(page.getByTestId("content")).toBeVisible();
        await expect(page.locator("html")).toHaveAttribute("data-theme", variant.theme);
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        );
        expect(overflow, `${path} overflows at ${variant.name}`).toBeLessThanOrEqual(1);
        await screenshot(
          page,
          `N-06-${variant.name}-${path.split("/").filter(Boolean).pop() ?? "page"}`,
        );
      }
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/#/library");
  } finally {
    await page.evaluate((theme) => {
      if (theme === null) localStorage.removeItem("gv_theme");
      else localStorage.setItem("gv_theme", theme);
    }, original.theme);
    await page.setViewportSize({ width: 1280, height: 900 });
  }
  await app.shot("N-06");
});

test("N-07 伴侣脚本与 API token（不阻塞切换） @parity", async ({ app }) => {
  const { page } = app;
  await page.goto("/#/settings");
  await page.locator('[data-settings-nav="account"]').click();
  await expect(page.getByTestId("api-token-status")).toBeVisible();
  await expect(page.getByTestId("api-token-generate")).toBeVisible();

  const status = await app.api.get<{ configured: boolean; created_at?: string | null }>(
    "/api/auth/api-token",
  );
  expect(typeof status.configured).toBe("boolean");
  const companion = await page.request.get("/galleryvault-companion.user.js");
  expect(companion.ok()).toBeTruthy();
  if (status.configured) {
    await expect(page.getByTestId("api-token-revoke")).toBeVisible();
  } else {
    await expect(page.getByTestId("api-token-revoke")).toHaveCount(0);
  }

  annotateUnverified(
    "token generate/revoke and the GM userscript against a sample page were not automated to avoid persisting a live credential in traces",
  );
  await app.shot("N-07");
});
