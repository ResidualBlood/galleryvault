import { test as base, expect, type Page } from "@playwright/test";
import { sessionEp } from "../../src/api/auth";
import { notificationsEp } from "../../src/api/system";

export interface MockState {
  /** When true every authenticated endpoint (and the session probe) returns 401. */
  expired: boolean;
  authenticated: boolean;
}

interface MockFixtures {
  mock: MockState;
}

const SESSION = {
  authenticated: true,
  auth_required: true,
  must_change_password: false,
  cookie_health: { state: "ok" },
};

async function installMockBackend(page: Page, state: MockState): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (state.expired) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "unauthorized" }),
      });
      return;
    }
    if (path === sessionEp.path) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(SESSION),
      });
      return;
    }
    if (path === notificationsEp.path) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], unread: 0 }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });

  await page.route("**/login", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html>" });
      return;
    }
    state.expired = false;
    state.authenticated = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });

  await page.route("**/logout", async (route) => {
    state.authenticated = false;
    state.expired = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });
}

export const test = base.extend<MockFixtures>({
  // eslint-disable-next-line no-empty-pattern -- Playwright requires destructuring here
  mock: async ({}, use) => {
    await use({ expired: false, authenticated: true });
  },
  page: async ({ page, mock }, use) => {
    await installMockBackend(page, mock);
    await use(page);
  },
});

export { expect };
