// smoke.spec.js — Phase 3 simple smoke test with playwright (5 core paths)
// run: npx playwright test smoke.spec.js --headed=false

const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.TEST_URL || 'http://localhost:8200';

test.describe('GalleryVault Frontend Smoke Suite', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL);
  });

  test('Path 1: Login UI & authentication check', async ({ page }) => {
    // If login is required, password input should be visible
    const pwInput = page.locator('input[name="password"]');
    if (await pwInput.isVisible()) {
      await pwInput.fill('password');
      await page.locator('button[type="submit"]').click();
      await page.waitForTimeout(500);
    }
    // Verify main app container is rendered
    await expect(page.locator('#app')).toBeVisible();
  });

  test('Path 2: Topbar 5 core links exist and have correct hrefs', async ({ page }) => {
    const topbar = page.locator('#topbar');
    // Topbar contains 5 core navigation links
    const expectedLinks = [
      { href: '#/browse' },
      { href: '#/library' },
      { href: '#/downloads' },
      { href: '#/favorites' },
      { href: '#/settings' },
    ];

    for (const item of expectedLinks) {
      const link = topbar.locator(`a[href="${item.href}"]`);
      await expect(link).toBeAttached();
    }
  });

  test('Path 3: Keyboard "/" shortcut focuses global search input', async ({ page }) => {
    const searchInput = page.locator('#global-search');
    await expect(searchInput).toBeAttached();
    // Press '/' key
    await page.keyboard.press('/');
    // Check if global search input is focused
    await expect(searchInput).toBeFocused();
  });

  test('Path 4: Language toggle switches UI language', async ({ page }) => {
    const langBtn = page.locator('button[data-action="toggle-lang"]');
    if (await langBtn.isVisible()) {
      const initialText = await langBtn.textContent();
      await langBtn.click();
      const newText = await langBtn.textContent();
      expect(newText).not.toBe(initialText);
      // Toggle back
      await langBtn.click();
    }
  });

  test('Path 5: Mobile hamburger menu toggle updates aria-expanded', async ({ page }) => {
    const hamburger = page.locator('button.hamburger[data-action="toggle-nav"]');
    if (await hamburger.isAttached()) {
      const initialExpanded = await hamburger.getAttribute('aria-expanded');
      await hamburger.click();
      const toggledExpanded = await hamburger.getAttribute('aria-expanded');
      expect(toggledExpanded).not.toBe(initialExpanded);
    }
  });
});
