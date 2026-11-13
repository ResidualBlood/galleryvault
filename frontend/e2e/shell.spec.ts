import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures/mock";

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

test("login submits and lands on the app shell @shell", async ({ page, mock }) => {
  const csp = watchConsole(page);
  mock.expired = true;

  await page.goto("/");
  await expect(page.getByTestId("login-card")).toBeVisible();
  await expect(page).toHaveURL(/#\/login/);

  await page.getByLabel("密码").fill("test-password");
  await page.getByTestId("login-submit").click();

  await expect(page.getByTestId("nav-drawer")).toBeVisible();
  await expect(page).toHaveURL(/#\/browse/);
  expect(csp).toEqual([]);
});

test("theme toggle cycles dark / light / system @shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();

  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "dark");

  await page.getByTestId("theme-toggle").click();
  await expect(html).toHaveAttribute("data-theme", "light");
  expect(await page.evaluate(() => localStorage.getItem("gv_theme"))).toBe("light");

  await page.getByTestId("theme-toggle").click();
  await expect(html).not.toHaveAttribute("data-theme");
  expect(await page.evaluate(() => localStorage.getItem("gv_theme"))).toBe("system");

  await page.getByTestId("theme-toggle").click();
  await expect(html).toHaveAttribute("data-theme", "dark");
});

test("language toggle switches zh / en and persists @shell", async ({ page }) => {
  await page.goto("/");
  const drawer = page.getByTestId("nav-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("浏览", { exact: true })).toBeVisible();

  await page.getByTestId("lang-toggle").click();
  await expect(drawer.getByText("Browse", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("gv_lang"))).toBe("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  await page.getByTestId("lang-toggle").click();
  await expect(drawer.getByText("浏览", { exact: true })).toBeVisible();
});

test("401 sends the user back to the login page @shell", async ({ page, mock }) => {
  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();

  mock.expired = true;
  await page.getByTestId("notifications").click();

  await expect(page.getByTestId("login-card")).toBeVisible();
  await expect(page).toHaveURL(/#\/login/);
});

test("navigation shape follows the three breakpoints @shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("nav-bottom")).toBeVisible();
  await expect(page.getByTestId("nav-rail")).toBeHidden();
  await expect(page.getByTestId("nav-drawer")).toBeHidden();

  await page.setViewportSize({ width: 700, height: 900 });
  await expect(page.getByTestId("nav-rail")).toBeVisible();
  await expect(page.getByTestId("nav-bottom")).toBeHidden();
  await expect(page.getByTestId("nav-drawer")).toBeHidden();

  await page.setViewportSize({ width: 1000, height: 900 });
  await expect(page.getByTestId("nav-drawer")).toBeVisible();
  await expect(page.getByTestId("nav-rail")).toBeHidden();
  await expect(page.getByTestId("nav-bottom")).toBeHidden();
});

test("screenshots cover dark/light x desktop/mobile @shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("content")).toBeVisible();

  const themes = ["dark", "light"] as const;
  const viewports = [
    { width: 1280, height: 900, label: "1280" },
    { width: 390, height: 844, label: "390" },
  ];

  for (const theme of themes) {
    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.evaluate((value) => localStorage.setItem("gv_theme", value), theme);
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.getByTestId("content")).toBeVisible();
      await page.screenshot({
        path: join(SHOTS, `shell-${theme}-${viewport.label}.png`),
        fullPage: true,
      });
    }
  }
});

test("console has zero CSP violations @shell", async ({ page }) => {
  const csp = watchConsole(page);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await expect(page.getByTestId("nav-drawer")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  // Below 840px theme / language / logout live in the navigation sheet
  // (audit SH-06: the topbar only keeps notifications + global controls).
  await page.getByTestId("bottom-more").click();
  const sheet = page.getByTestId("nav-sheet");
  await expect(sheet).toBeVisible();
  await sheet.getByTestId("theme-toggle").click();
  await sheet.getByTestId("lang-toggle").click();
  await expect(page.getByTestId("nav-bottom")).toBeVisible();

  expect(csp).toEqual([]);
  expect(pageErrors).toEqual([]);
});
