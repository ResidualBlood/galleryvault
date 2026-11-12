import { mkdirSync } from "node:fs";
import { createServer as createTcpServer } from "node:net";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createServer, type ViteDevServer } from "vite";

const PROJECT_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SHOTS = process.env.GV_SHOTS || join(process.cwd(), "test-results/shots");
const GROUPS = [
  "appearance",
  "reader",
  "network",
  "online",
  "library",
  "download",
  "favorites",
  "archive",
  "tags",
  "notifications",
  "account",
  "integrations",
  "system",
] as const;
const SECRET_SENTINEL = "do-not-render-this-secret";

let vite: ViteDevServer;
let HARNESS = "";

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createTcpServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      const port = typeof address === "object" && address ? address.port : 0;
      probe.close(() => resolve(port));
    });
  });
}

function watchConsole(page: Page): string[] {
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

function harnessUrl(
  view: string,
  options: { theme?: "dark" | "light"; quality?: "resample" | "original" } = {},
): string {
  const params = new URLSearchParams({ view, theme: options.theme ?? "dark" });
  if (options.quality) params.set("quality", options.quality);
  return `${HARNESS}?${params.toString()}`;
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true });
}

async function clearSecrets(page: Page): Promise<void> {
  const inputs = await page.locator('input[type="password"]').all();
  for (const input of inputs) {
    if (await input.isVisible()) await input.fill("");
  }
}

async function selectGroup(page: Page, id: string): Promise<void> {
  const nav = page.locator(`[data-settings-nav="${id}"]`);
  if (!(await nav.isVisible())) {
    await page.getByTestId("settings-back").click();
  }
  await nav.click();
  await expect(page.locator(`[data-settings-group="${id}"]`)).toBeVisible();
}

async function openSettings(page: Page): Promise<void> {
  await page.goto(harnessUrl("settings"));
  await expect(page.getByTestId("settings-page")).toBeVisible();
  await expect(page.getByTestId("settings-nav")).toBeVisible();
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  const port = await freePort();
  vite = await createServer({
    root: PROJECT_ROOT,
    logLevel: "error",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  await vite.listen();
  HARNESS = `http://127.0.0.1:${port}/e2e/fixtures/settings-sys/harness.html`;
});

test.afterAll(async () => {
  await vite?.close();
});

test.beforeEach(async ({ page }) => {
  await page.context().addCookies([
    { name: "galleryvault_csrf", value: "test-csrf", url: HARNESS },
  ]);
});

test.describe("settings & system @settings-sys", () => {
  test("saves one group with only its changed keys", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await openSettings(page);

    await selectGroup(page, "download");
    await page.locator('[data-setting-key="download_concurrency"] input').fill("8");
    await page.getByTestId("settings-save").click();
    await expect.poll(() => mock.posts.filter((entry) => entry.path === "/api/settings").length).toBe(1);
    expect(mock.posts[0]?.body).toEqual({ download_concurrency: 8 });

    await selectGroup(page, "appearance");
    await page.locator('[data-setting-key="title_display"] select').selectOption("english");
    await page.getByTestId("settings-save").click();
    await expect.poll(() => mock.posts.filter((entry) => entry.path === "/api/settings").length).toBe(2);
    expect(mock.posts[1]?.body).toEqual({ title_display: "english" });
  });

  test("download_root needs the current password before it is submitted", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await openSettings(page);

    await selectGroup(page, "download");
    await page.locator('[data-setting-key="download_root"] input').fill("/srv/new-downloads");
    await page.getByTestId("settings-save").click();

    await expect(page.getByTestId("security-confirm")).toBeVisible();
    expect(mock.posts.filter((entry) => entry.path === "/api/settings")).toHaveLength(0);

    const dialog = page.getByTestId("security-confirm");
    await dialog.locator('input[type="password"]').fill("hunter2");
    await page.getByTestId("security-confirm-submit").click();

    await expect(page.getByTestId("security-confirm")).toBeHidden();
    await expect.poll(() => mock.posts.filter((entry) => entry.path === "/api/settings").length).toBe(1);
    expect(mock.posts[0]?.body).toMatchObject({
      download_root: "/srv/new-downloads",
      current_password: "hunter2",
    });
    await clearSecrets(page);
  });

  test("search locates any key and jumps to its group", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    await openSettings(page);

    await page.getByTestId("settings-search").locator("input").fill("socks5_proxy");
    const result = page.locator('[data-result-key="socks5_proxy"]');
    await expect(result).toBeVisible();
    await result.click();

    await expect(page.locator('[data-settings-group="network"]')).toBeVisible();
    await expect(page.locator('[data-setting-key="socks5_proxy"]')).toBeVisible();
  });

  test("API token plaintext is shown exactly once", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    await openSettings(page);

    await selectGroup(page, "account");
    await expect(page.getByTestId("api-token-status")).toContainText("尚未生成");
    await page.getByTestId("api-token-generate").click();
    await expect(page.getByTestId("api-token-once")).toBeVisible();
    const token = "gvt_TEST_ONLY_TOKEN_9f3c";
    await expect(page.getByTestId("api-token-plaintext")).toHaveText(token);

    const bodyText = await page.locator("body").innerText();
    expect(bodyText.split(token)).toHaveLength(2);

    await page.getByTestId("api-token-once").getByRole("button", { name: "我已保存，隐藏" }).click();
    await expect(page.getByTestId("api-token-once")).toBeHidden();
    await expect(page.getByTestId("api-token-status")).toContainText("已生成");

    await selectGroup(page, "network");
    await selectGroup(page, "account");
    expect(await page.locator("body").innerText()).not.toContain(token);
  });

  test("password, cookie and token fields never reach DOM text or screenshots", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    await openSettings(page);

    await selectGroup(page, "account");
    const current = page.locator('[data-settings-section="password"] input[type="password"]').first();
    await current.fill(SECRET_SENTINEL);

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toContain(SECRET_SENTINEL);
    expect(await page.evaluate(() => Object.values(localStorage).join("\n"))).not.toContain(
      SECRET_SENTINEL,
    );

    await expect(current).toHaveAttribute("type", "password");
    await selectGroup(page, "notifications");
    await expect(page.locator('[data-setting-key="telegram_bot_token"] input')).toHaveAttribute(
      "type",
      "password",
    );
    await expect(page.locator('[data-setting-key="telegram_bot_token"] input')).toHaveValue("");

    await selectGroup(page, "download");
    await page.locator('[data-setting-key="download_root"] input').fill("/srv/screenshot-check");
    await page.getByTestId("settings-save").click();
    await expect(page.getByTestId("security-confirm")).toBeVisible();
    await page
      .getByTestId("security-confirm")
      .locator('input[type="password"]')
      .fill(SECRET_SENTINEL);

    await clearSecrets(page);
    await page.getByTestId("security-confirm").getByRole("button", { name: "取消" }).click();
    await selectGroup(page, "account");
    await clearSecrets(page);
    await shot(page, "settings-account-credentials-cleared");
    expect(await page.locator("body").innerText()).not.toContain(SECRET_SENTINEL);
  });

  test("screenshots every settings group in both themes and viewports", async ({ page }) => {
    test.setTimeout(240_000);
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page);
    const csp = watchConsole(page);

    for (const theme of ["dark", "light"] as const) {
      for (const viewport of [
        { width: 1280, height: 900, label: "desktop-1280" },
        { width: 390, height: 844, label: "mobile-390" },
      ]) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(harnessUrl("settings", { theme }));
        await expect(page.getByTestId("settings-page")).toBeVisible();
        for (const group of GROUPS) {
          await selectGroup(page, group);
          await clearSecrets(page);
          await shot(page, `settings-${group}-${theme}-${viewport.label}`);
        }
      }
    }
    expect(csp).toEqual([]);
  });

  test("screenshots logs, welcome, archive, notifications and system widgets", async ({ page }) => {
    test.setTimeout(240_000);
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page, { cookieState: "not_logged_in" });
    const csp = watchConsole(page);

    const surfaces = [
      "logs",
      "welcome",
      "archive",
      "notifications",
      "archive-dialog",
      "cookie-banner",
      "global-controls",
    ];
    for (const theme of ["dark", "light"] as const) {
      for (const viewport of [
        { width: 1280, height: 900, label: "desktop-1280" },
        { width: 390, height: 844, label: "mobile-390" },
      ]) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        for (const view of surfaces) {
          await page.goto(harnessUrl(view, { theme }));
          await expect(page.getByTestId(`${view === "cookie-banner" ? "cookie-health-banner" : view === "global-controls" ? "global-controls" : view === "archive-dialog" ? "archive-dialog" : view === "notifications" ? "notification-panel" : view === "archive" ? "archive-page" : view === "welcome" ? "welcome-page" : "logs-page"}`)).toBeVisible();
          await clearSecrets(page);
          await shot(page, `system-${view}-${theme}-${viewport.label}`);
        }
      }
    }
    expect(csp).toEqual([]);
  });

  test("logs filter, runtime level, download, clear and task cancel", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await page.goto(harnessUrl("logs"));
    await expect(page.getByTestId("logs-page")).toBeVisible();

    await page.getByTestId("logs-cancel").click();
    await expect
      .poll(() => mock.posts.some((entry) => entry.path === "/api/logs/scan/cancel"))
      .toBe(true);

    await page.getByTestId("logs-tab-system").click();
    await expect(page.locator('[data-testid="syslog-level"] select')).toHaveValue("INFO");
    await expect(page.locator('[data-testid="syslog-download"]')).toHaveAttribute(
      "href",
      "/api/system/logs/download",
    );
    await expect(page.locator('[data-testid="syslog-list"] [data-level="ERROR"]').first()).toBeVisible();

    await page.locator('[data-testid="syslog-level"] select').selectOption("DEBUG");
    await expect
      .poll(() => mock.posts.filter((entry) => entry.path === "/api/system/logs/level").length)
      .toBe(1);
    expect(mock.posts.find((entry) => entry.path === "/api/system/logs/level")?.body).toEqual({
      level: "DEBUG",
    });

    await page.getByTestId("syslog-clear").click();
    await page.getByTestId("syslog-clear-confirm").click();
    await expect
      .poll(() => mock.requests.some((entry) => entry.method === "DELETE" && entry.path === "/api/system/logs"))
      .toBe(true);
  });

  test("welcome onboarding changes password, saves connection fields, scans and finishes", async ({
    page,
  }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await page.goto(harnessUrl("welcome"));
    await expect(page.getByTestId("welcome-page")).toBeVisible();

    const passwordInputs = page.locator('[data-testid="welcome-password"] input[type="password"]');
    await passwordInputs.nth(0).fill("old-password");
    await passwordInputs.nth(1).fill("new-password");
    await passwordInputs.nth(2).fill("new-password");
    await page.getByTestId("welcome-save-password").click();
    await expect
      .poll(() => mock.posts.some((entry) => entry.path === "/api/auth/change-password"))
      .toBe(true);
    expect(mock.posts.find((entry) => entry.path === "/api/auth/change-password")?.body).toEqual({
      current: "old-password",
      new: "new-password",
    });

    await page.locator('[data-testid="welcome-base-url"] select').selectOption("https://e-hentai.org");
    const siteInputs = page.locator('[data-testid="welcome-site"] input[type="password"]');
    await siteInputs.nth(0).fill(SECRET_SENTINEL);
    await page.getByTestId("welcome-save-site").click();
    await expect
      .poll(() => mock.posts.filter((entry) => entry.path === "/api/settings").length)
      .toBe(1);
    expect(mock.posts.find((entry) => entry.path === "/api/settings")?.body).toEqual({
      exhentai_base_url: "https://e-hentai.org",
      ipb_member_id: SECRET_SENTINEL,
    });
    await expect(siteInputs.nth(0)).toHaveValue("");

    await page.getByTestId("welcome-scan").click();
    await expect.poll(() => mock.posts.some((entry) => entry.path === "/api/scan")).toBe(true);
    await page.getByTestId("welcome-check-favs").click();
    await expect
      .poll(() => mock.posts.some((entry) => entry.path === "/api/favorites/check-all"))
      .toBe(true);

    expect(await page.locator("body").innerText()).not.toContain(SECRET_SENTINEL);
    await page.getByTestId("welcome-finish-button").click();
    await expect(page.locator("body")).toHaveAttribute("data-route", "browse");
  });

  test("archive page starts, cancels and purges", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await page.goto(harnessUrl("archive"));
    await expect(page.getByTestId("archive-page")).toBeVisible();
    await expect(page.getByTestId("archive-status")).toBeVisible();

    await page.getByTestId("archive-start").click();
    await expect.poll(() => mock.posts.some((entry) => entry.path === "/api/archive")).toBe(true);
    await expect(page.getByTestId("archive-cancel")).toBeEnabled();
    await page.getByTestId("archive-cancel").click();
    await expect
      .poll(() => mock.posts.some((entry) => entry.path === "/api/logs/archive/cancel"))
      .toBe(true);

    await page.getByTestId("archive-purge").click();
    await page.getByTestId("archive-purge-confirm").click();
    await expect
      .poll(() => mock.posts.some((entry) => entry.path === "/api/system/purge-archived-sources"))
      .toBe(true);
  });

  test("archive dialog previews with the configured default quality", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await page.goto(harnessUrl("archive-dialog", { quality: "original" }));
    const dialog = page.getByTestId("archive-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("select")).toHaveValue("original");
    await expect(dialog.locator(".archive-dialog__item")).toHaveCount(2);
    await expect(dialog).toContainText("GP 余额");
    expect(mock.posts.find((entry) => entry.path === "/api/archives/preview")?.body).toEqual({
      gids: [101, 102],
    });

    await page.getByTestId("archive-dialog-confirm").click();
    const confirmed = await page.evaluate(() => window.__GV_ARCHIVE_CONFIRM__);
    expect(confirmed).toEqual({ gids: [101, 102], quality: "original" });
  });

  test("notification panel shows unread items and supports read/clear", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await page.goto(harnessUrl("notifications"));
    const panel = page.getByTestId("notification-panel");
    await expect(panel).toBeVisible();
    await expect(page.getByTestId("notification-badge")).toHaveText("2");
    await expect(panel.locator("[data-notification-id]")).toHaveCount(2);

    await panel.getByRole("button", { name: "全部已读" }).click();
    await expect.poll(() => mock.posts.some((entry) => entry.path === "/api/notifications/read")).toBe(
      true,
    );
    await expect(page.getByTestId("notification-badge")).toBeHidden();

    await panel.getByRole("button", { name: "清空" }).click();
    await expect.poll(() => mock.posts.some((entry) => entry.path === "/api/notifications/clear")).toBe(
      true,
    );
    await expect(panel).toContainText("暂无通知");
  });

  test("cookie health banner appears for a broken cookie and can be dismissed", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    await mockSettingsBackend(page, { cookieState: "not_logged_in" });
    await page.goto(harnessUrl("cookie-banner"));
    const banner = page.getByTestId("cookie-health-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute("data-cookie-state", "not_logged_in");
    await expect(banner).toContainText("E-Hentai Cookie 异常");
    await expect(banner.getByRole("link", { name: "前往设置" })).toHaveAttribute(
      "href",
      "#/settings",
    );
    await expect(banner).toBeVisible();
    await page.getByTestId("cookie-health-banner").getByRole("button", { name: "忽略" }).click();
    await expect(page.getByTestId("cookie-health-banner")).toBeHidden();
  });

  test("global controls pause, scan and purge", async ({ page }) => {
    const { mockSettingsBackend } = await import("./fixtures/settings-sys/mock");
    const mock = await mockSettingsBackend(page);
    await page.goto(harnessUrl("global-controls"));
    await expect(page.getByTestId("global-controls")).toBeVisible();

    await page.getByTestId("global-pause").click();
    await expect.poll(() => mock.requests.some((entry) => entry.path === "/api/pause" && entry.method === "POST")).toBe(true);
    expect(
      mock.requests.find((entry) => entry.path === "/api/pause" && entry.method === "POST")?.body,
    ).toEqual({ paused: true });
    await expect(page.getByTestId("global-paused")).toBeVisible();

    await page.getByTestId("global-scan").click();
    await expect.poll(() => mock.posts.some((entry) => entry.path === "/api/scan")).toBe(true);

    await page.getByTestId("global-purge").click();
    await page.getByTestId("global-purge-confirm").click();
    await expect
      .poll(() => mock.posts.some((entry) => entry.path === "/api/system/purge-archived-sources"))
      .toBe(true);
  });
});
