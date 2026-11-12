import { expect, test } from "@playwright/test";
import { sessionEp } from "../../src/api/auth";

/**
 * @smoke — read-only smoke test for the shared test environment.
 * Writers must not run this (PLAN §5.2); the tester runs it after integration.
 */
test("smoke: shell loads and the session endpoint responds @smoke", async ({ page }) => {
  const password = process.env.GV_E2E_PASSWORD;
  const base = process.env.GV_E2E_BASE;

  test.skip(!base || !password, "GV_E2E_BASE / GV_E2E_PASSWORD not set");

  await page.goto("/");
  const loginCard = page.getByTestId("login-card");
  if (await loginCard.isVisible().catch(() => false)) {
    await page.getByLabel(/密码|Password/).fill(password as string);
    await page.getByTestId("login-submit").click();
  }

  await expect(page.getByTestId("content")).toBeVisible({ timeout: 20_000 });
  const session = await page.request.get(sessionEp.path);
  expect(session.ok()).toBeTruthy();
  const body = (await session.json()) as { authenticated?: boolean };
  expect(body.authenticated).toBe(true);
});
