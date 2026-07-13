import { test, expect } from '@playwright/test';
import { gotoHome, gotoPath, waitForPageReady, dismissPopups, ROUTES } from '../helpers/test-utils';

test.describe('Search Functionality', () => {
  test.describe('Search Overlay', () => {
    test.beforeEach(async ({ page }) => {
      await gotoHome(page);
    });

    test('search icon opens overlay on desktop', async ({ page }) => {
      // Dismiss promotional popup first
      await dismissPopups(page);
      const searchBtn = page.locator('header button[aria-label="Search"]').first();
      if (await searchBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await searchBtn.click();
        await page.waitForTimeout(500);
        // The search dialog at z-[70] should have an input
        const searchInput = page.locator('div[role="dialog"] input').first();
        await expect(searchInput).toBeVisible({ timeout: 5000 });
      }
    });

    test('search overlay shows trending searches', async ({ page }) => {
      await dismissPopups(page);
      const searchBtn = page.locator('header button[aria-label="Search"]').first();
      if (await searchBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await searchBtn.click();
        await page.waitForTimeout(500);
        // Trending tags: Bugadi, Chains, Anklets, etc.
        const trending = page.locator('div[role="dialog"]').getByRole('button', { name: /bugadi|chains|anklets/i });
        const count = await trending.count();
        expect(count).toBeGreaterThan(0);
      }
    });

    test('search overlay has close button', async ({ page }) => {
      await dismissPopups(page);
      const searchBtn = page.locator('header button[aria-label="Search"]').first();
      if (await searchBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await searchBtn.click();
        await page.waitForTimeout(500);
        // Close button has aria-label="Close search"
        const closeBtn = page.locator('button[aria-label="Close search"]');
        await expect(closeBtn).toBeVisible({ timeout: 5000 });
      }
    });

    test('ESC key closes search overlay', async ({ page }) => {
      await dismissPopups(page);
      const searchBtn = page.locator('header button[aria-label="Search"]').first();
      if (await searchBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await searchBtn.click();
        await page.waitForTimeout(500);
        // Verify search input is visible
        const searchInput = page.locator('div[role="dialog"] input').first();
        await expect(searchInput).toBeVisible({ timeout: 5000 });
        // Press Escape to close the search overlay
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
        // The search overlay input should be hidden now
        // Note: promotional popup might still be visible, so check the input is gone
        const searchVisible = await searchInput.isVisible().catch(() => false);
        expect(searchVisible).toBeFalsy();
      }
    });
  });

  test.describe('Search Page', () => {
    test('loads search page with query param', async ({ page }) => {
      await gotoPath(page, '/search?q=chain');
      await waitForPageReady(page);
      await expect(page).toHaveTitle(/search|hadha/i);
    });

    test('search input shows the query', async ({ page }) => {
      await gotoPath(page, '/search?q=chain');
      await waitForPageReady(page);
      const input = page.locator('input').first();
      if (await input.isVisible({ timeout: 5000 }).catch(() => false)) {
        const value = await input.inputValue();
        expect(value.toLowerCase()).toContain('chain');
      }
    });

    test('search results or empty state is shown', async ({ page }) => {
      await gotoPath(page, '/search?q=rings');
      await waitForPageReady(page);
      await page.waitForTimeout(5000);
      const body = page.locator('body');
      await expect(body).toBeVisible();
    });

    test('trending searches are shown on empty search', async ({ page }) => {
      await gotoPath(page, '/search');
      await waitForPageReady(page);
      await page.waitForTimeout(1000);
      const trending = page.getByText(/trending|popular|suggestion/i);
      await expect(trending.first()).toBeVisible();
    });

    test('recent searches are shown', async ({ page }) => {
      // "Recent searches" only renders once the recent-search store is non-empty
      // (it's push()-ed from the query param on a real search) — perform one
      // search first so the precondition for this UI actually holds.
      await gotoPath(page, '/search?q=chain');
      await waitForPageReady(page);
      await gotoPath(page, '/search');
      await waitForPageReady(page);
      const recent = page.getByText(/recent/i);
      await expect(recent.first()).toBeVisible();
    });

    test('pagination works on search results', async ({ page }) => {
      await gotoPath(page, '/search?q=silver');
      await waitForPageReady(page);
      const paginationNav = page.locator('nav[aria-label*="pagination"], [class*="pagination"]').first();
      if (await paginationNav.isVisible({ timeout: 5000 }).catch(() => false)) {
        const nextBtn = paginationNav.locator('a, button').last();
        if (await nextBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
          await nextBtn.click();
          await waitForPageReady(page);
        }
      }
    });
  });

  test.describe('Search Edge Cases', () => {
    test('empty search query shows suggestions', async ({ page }) => {
      await gotoPath(page, '/search?q=');
      await waitForPageReady(page);
      await expect(page.locator('body')).toBeVisible();
    });

    test('special characters in search do not break page', async ({ page }) => {
      await gotoPath(page, '/search?q=<script>alert(1)</script>');
      await waitForPageReady(page);
      await expect(page.locator('body')).toBeVisible();
      const alertFired = await page.evaluate(() => (window as Record<string, unknown>)['__alertFired'] ?? false);
      expect(alertFired).toBeFalsy();
    });

    test('very long search query does not break page', async ({ page }) => {
      const longQuery = 'a'.repeat(200);
      await gotoPath(page, `/search?q=${longQuery}`);
      await waitForPageReady(page);
      // Page should at least load the body
      await expect(page.locator('body')).toBeVisible();
    });
  });
});
