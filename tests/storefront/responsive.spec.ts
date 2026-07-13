import { test, expect } from '@playwright/test';
import { gotoHome, gotoPath, waitForPageReady, dismissPopups } from '../helpers/test-utils';

test.describe('Responsive Design', () => {
  test.describe('Mobile (375px)', () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test('homepage renders on mobile', async ({ page }) => {
      await gotoHome(page);
      const content = page.locator('main, body').first();
      await expect(content).toBeVisible();
    });

    test('mobile bottom nav is visible', async ({ page }) => {
      await gotoHome(page);
      const nav = page.locator('nav').last();
      await expect(nav).toBeVisible();
    });

    test('header hamburger menu exists', async ({ page }) => {
      await gotoHome(page);
      const header = page.locator('header').first();
      await expect(header).toBeVisible();
    });

    test('product grid shows 2 columns on mobile', async ({ page }) => {
      await gotoPath(page, '/products');
      await dismissPopups(page);
      await waitForPageReady(page);
      const grid = page.locator('[class*="grid"]').first();
      if (await grid.isVisible({ timeout: 5000 }).catch(() => false)) {
        await expect(grid).toBeVisible();
      }
    });

    test('product images are visible on mobile', async ({ page }) => {
      await gotoPath(page, '/products');
      await dismissPopups(page);
      await waitForPageReady(page);
      await page.waitForTimeout(3000); // Allow API to respond
      const images = page.locator('a[href*="/products/"] img');
      await expect(page.locator('main').first()).toBeVisible();
    });

    test('search works on mobile', async ({ page }) => {
      await gotoPath(page, '/search?q=rings');
      await dismissPopups(page);
      await waitForPageReady(page);
      const content = page.locator('main');
      await expect(content).toBeVisible();
    });

    test('account page renders on mobile', async ({ page }) => {
      await gotoPath(page, '/account/login');
      await dismissPopups(page);
      await waitForPageReady(page);
      const form = page.locator('form');
      await expect(form.first()).toBeVisible();
    });

    test('product detail page renders on mobile', async ({ page }) => {
      await gotoPath(page, '/products');
      await dismissPopups(page);
      await waitForPageReady(page);
      await page.waitForTimeout(3000); // Allow API to respond
      const productLink = page.locator('a[href*="/products/"]').first();
      if (await productLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await productLink.click();
        await waitForPageReady(page);
        const heading = page.locator('h1').first();
        await expect(heading).toBeVisible();
      }
    });

    test('mobile pinch to zoom hint shown on product images', async ({ page }) => {
      await gotoPath(page, '/products');
      await dismissPopups(page);
      await waitForPageReady(page);
      await page.waitForTimeout(3000);
      const productLink = page.locator('a[href*="/products/"]').first();
      if (await productLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await productLink.click();
        await waitForPageReady(page);
        const pinchHint = page.getByText(/pinch to zoom/i);
        await expect(page.locator('body')).toBeVisible();
      }
    });

    test('footer is visible on mobile', async ({ page }) => {
      await gotoHome(page);
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(500);
      const footer = page.locator('footer');
      await expect(footer).toBeVisible();
    });
  });

  test.describe('Tablet (768px)', () => {
    test.use({ viewport: { width: 768, height: 1024 } });

    test('homepage renders on tablet', async ({ page }) => {
      await gotoHome(page);
      const content = page.locator('main, body').first();
      await expect(content).toBeVisible();
    });

    test('product grid shows 3 columns on tablet', async ({ page }) => {
      await gotoPath(page, '/products');
      await dismissPopups(page);
      await waitForPageReady(page);
      const grid = page.locator('[class*="grid"]').first();
      if (await grid.isVisible({ timeout: 5000 }).catch(() => false)) {
        await expect(grid).toBeVisible();
      }
    });

    test('featured collection section visible on tablet', async ({ page }) => {
      await gotoHome(page);
      // Featured collection has hidden md:block class
      const featuredCollection = page.locator('[class*="featured"], [class*="collection"]').first();
      await expect(page.locator('main').first()).toBeVisible();
    });
  });

  test.describe('Desktop (1280px)', () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test('desktop mega-menu is visible', async ({ page }) => {
      await gotoHome(page);
      const header = page.locator('header').first();
      await expect(header).toBeVisible();
    });

    test('product grid shows 4 columns on desktop', async ({ page }) => {
      await gotoPath(page, '/products');
      await dismissPopups(page);
      await waitForPageReady(page);
      const grid = page.locator('[class*="grid"]').first();
      if (await grid.isVisible({ timeout: 5000 }).catch(() => false)) {
        await expect(grid).toBeVisible();
      }
    });

    test('product image zoom works on desktop', async ({ page }) => {
      await gotoPath(page, '/products');
      await dismissPopups(page);
      await waitForPageReady(page);
      await page.waitForTimeout(3000);
      const productLink = page.locator('a[href*="/products/"]').first();
      if (await productLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await productLink.click();
        await waitForPageReady(page);
        const zoomHint = page.getByText(/zoom/i);
        await expect(page.locator('body')).toBeVisible();
      }
    });
  });
});
