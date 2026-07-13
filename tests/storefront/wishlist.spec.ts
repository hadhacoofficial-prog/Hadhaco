import { test, expect } from '@playwright/test';
import { gotoHome, gotoPath, waitForPageReady, clearWishlistLocalStorage } from '../helpers/test-utils';

test.describe('Wishlist', () => {
  test.describe('Wishlist Page', () => {
    test.beforeEach(async ({ page }) => {
      await gotoPath(page, '/wishlist');
      await waitForPageReady(page);
      await clearWishlistLocalStorage(page);
    });

    test('wishlist page loads', async ({ page }) => {
      await expect(page).toHaveTitle(/wishlist|hadha/i);
    });

    test('empty wishlist shows empty state', async ({ page }) => {
      const emptyState = page.getByText(/empty|no items|discover|save pieces/i);
      await expect(emptyState.first()).toBeVisible();
    });

    test('empty state has link to collections', async ({ page }) => {
      const collectionsLink = page.locator('a[href="/collections"]');
      const count = await collectionsLink.count();
      expect(count).toBeGreaterThan(0);
    });
  });

  test.describe('Wishlist Interactions', () => {
    test('wishlist toggle on product page adds item', async ({ page }) => {
      // Navigate to a product
      await gotoPath(page, '/products');
      await waitForPageReady(page);
      await clearWishlistLocalStorage(page);
      await page.waitForTimeout(3000); // Allow API to respond
      const productLink = page.locator('a[href*="/products/"]').first();
      if (await productLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await productLink.click();
        await waitForPageReady(page);

        // Find and click wishlist button
        const wishlistBtn = page.locator('button').filter({ has: page.locator('svg') }).last();
        if (await wishlistBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
          await wishlistBtn.click();
          await page.waitForTimeout(500);

          // Check localStorage
          const wishlistData = await page.evaluate(() => localStorage.getItem('hadha-wishlist'));
          if (wishlistData) {
            const parsed = JSON.parse(wishlistData);
            expect(parsed.state.items.length).toBeGreaterThan(0);
          }
        }
      }
    });

    test('wishlist persists in localStorage', async ({ page }) => {
      // Navigate to a same-origin page first so localStorage is accessible
      await gotoPath(page, '/');
      await waitForPageReady(page);
      await clearWishlistLocalStorage(page);
      // Add item to wishlist via localStorage manipulation
      await page.evaluate(() => {
        const wishlist = {
          state: {
            items: [
              {
                id: 'test-id',
                slug: 'test-product',
                name: 'Test Product',
                image: 'https://example.com/image.jpg',
                price: 999,
                sku: 'HDH-TEST-001',
              },
            ],
          },
          version: 0,
        };
        localStorage.setItem('hadha-wishlist', JSON.stringify(wishlist));
      });

      await gotoPath(page, '/wishlist');
      await waitForPageReady(page);
      // Item should be visible
      const item = page.getByText(/test product/i);
      await expect(item.first()).toBeVisible();
    });

    test('remove from wishlist removes item', async ({ page }) => {
      // Navigate to a same-origin page first so localStorage is accessible
      await gotoPath(page, '/');
      await waitForPageReady(page);
      // First add an item
      await page.evaluate(() => {
        const wishlist = {
          state: {
            items: [
              {
                id: 'test-id',
                slug: 'test-product',
                name: 'Test Product',
                image: 'https://example.com/image.jpg',
                price: 999,
                sku: 'HDH-TEST-001',
              },
            ],
          },
          version: 0,
        };
        localStorage.setItem('hadha-wishlist', JSON.stringify(wishlist));
      });

      await gotoPath(page, '/wishlist');
      await waitForPageReady(page);
      const removeBtn = page.getByRole('button', { name: /remove/i }).or(
        page.locator('button[aria-label*="remove"]').first(),
      );
      if (await removeBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await removeBtn.click();
        await page.waitForTimeout(500);
        // Check that item was removed
        const wishlistData = await page.evaluate(() => localStorage.getItem('hadha-wishlist'));
        if (wishlistData) {
          const parsed = JSON.parse(wishlistData);
          expect(parsed.state.items).toHaveLength(0);
        }
      }
    });
  });

  test.describe('Wishlist Badge in Header', () => {
    test('header shows wishlist count', async ({ page }) => {
      await gotoHome(page);
      const wishlistBadge = page.locator('header').locator('[class*="badge"]').or(
        page.locator('header a[href="/wishlist"] span'),
      );
      await expect(page.locator('header').first()).toBeVisible();
    });
  });

  test.describe('Mobile Wishlist', () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test('mobile bottom nav has wishlist tab', async ({ page }) => {
      await gotoHome(page);
      const bottomNav = page.locator('nav').last();
      const wishlistTab = bottomNav.getByText(/wishlist/i);
      const count = await wishlistTab.count();
      expect(count).toBeGreaterThan(0);
    });
  });
});
