import { BASE_URL, expect, requirePassword, test } from "./support";

/**
 * G-01: login, logout, expired-session redirect and the onboarding route.
 *
 * The onboarding page is inspected without submitting a password change:
 * changing the shared test password would invalidate every later spec and the
 * tester's own credentials.
 */
test("G-01 登录 / 会话 / 首次引导 @parity", async ({ app, browser }) => {
  const password = requirePassword();
  const anonymous = await browser.newContext({
    baseURL: BASE_URL,
    viewport: { width: 1280, height: 900 },
  });
  const page = await anonymous.newPage();

  try {
    await page.goto("/");
    await expect(page.getByTestId("login-card")).toBeVisible({ timeout: 20_000 });
    await page.getByLabel(/密码|password/i).fill(password);
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("content")).toBeVisible({ timeout: 20_000 });

    await page.getByTestId("logout").click();
    await expect(page.getByTestId("login-card")).toBeVisible({ timeout: 20_000 });

    // Expired / invalid session cookie must land on the login page, not a
    // blank shell or an API error page.
    await page.context().addCookies([
      { name: "galleryvault_session", value: "invalid", url: BASE_URL },
    ]);
    await page.goto("/");
    await expect(page.getByTestId("login-card")).toBeVisible({ timeout: 20_000 });
  } finally {
    await anonymous.close();
  }

  await app.page.goto("/#/welcome");
  await expect(app.page.getByTestId("welcome-page")).toBeVisible({ timeout: 20_000 });
  await expect(app.page.getByTestId("welcome-password")).toBeVisible();
  await expect(app.page.getByTestId("welcome-site")).toBeVisible();
  await expect(app.page.getByTestId("welcome-finish")).toBeVisible();
  await expect(app.page.getByTestId("welcome-current-password")).toBeVisible();
  await expect(app.page.getByTestId("welcome-base-url")).toBeVisible();
  await app.shot("G-01");
});
