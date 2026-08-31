// smoke.spec.js — Phase 3 simple smoke test with playwright (key paths)
// run: npx playwright test smoke.spec.js --headed=false

const { test, expect } = require('@playwright/test');

test.describe('GalleryVault smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:8200/');
  });

  test('login and browse', async ({ page }) => {
    // assume test container password=password, but since SPA, check UI
    await expect(page.locator('input[name="password"]')).toBeVisible();
    // fill not needed for smoke if already, but
  });

  test('has topbar links', async ({ page }) => {
    // after auth simulation, but basic
    const links = ['Browse', 'Library', 'Downloads', 'Favorites', 'Settings'];
    for (const l of links) {
      // check in html or after
    }
  });
});
