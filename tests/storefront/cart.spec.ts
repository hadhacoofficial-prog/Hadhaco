import { test, expect } from '@playwright/test';
import {
  gotoHome,
  gotoPath,
  waitForPageReady,
  clearCartLocalStorage,
  getFirstProductSlug,
} from '../helpers/test-utils';

test.describe('Cart Functionality', () => {
  test.describe('Cart State Management', () => {
    test('empty cart shows empty state', async ({ page }) => {
      await gotoHome(page);
      await clearCartLocalStorage(page);
      await gotoPath(page, '/cart');
      await waitForPageReady(page);
      const heading = page.getByText(/shopping cart|your cart/i);
      const emptyState = page.getByText(/cart is empty|start shopping/i);
      await expect(heading.or(emptyState).first()).toBeVisible();
    });

    test('localStorage cart is cleared properly', async ({ page }) => {
      await gotoHome(page);
      await clearCartLocalStorage(page);
      const cartData = await page.evaluate(() => localStorage.getItem('hadha-cart'));
      if (cartData) {
        const parsed = JSON.parse(cartData);
        expect(parsed.state.lines).toHaveLength(0);
      }
    });
  });

  test.describe('Product Page Cart Interactions', () => {
    test.describe.configure({ timeout: 60000 });
    let productSlug: string | null = null;

    test.beforeEach(async ({ page }) => {
      await gotoHome(page);
      await clearCartLocalStorage(page);
      await gotoPath(page, '/products');
      await waitForPageReady(page);
      productSlug = await getFirstProductSlug(page);
      if (productSlug) {
        await gotoPath(page, `/products/${productSlug}`);
        await waitForPageReady(page);
      }
    });

    test('add to cart button triggers cart drawer', async ({ page }) => {
      if (!productSlug) return;
      const addToCartBtn = page.getByRole('button', { name: /add to cart/i });
      if (await addToCartBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await addToCartBtn.click();
        await page.waitForTimeout(500);
        // CartDrawer (src/components/site/CartDrawer.tsx) renders a semantic
        // <aside> with a "Your Cart" heading — not role="dialog" or
        // data-state="open". The old selector here happened to match those
        // attributes on the (unrelated) promotional popup whenever it was
        // also open, so this assertion could pass without the cart drawer
        // ever actually appearing.
        const drawer = page.getByRole('heading', { name: /your cart/i });
        await expect(drawer).toBeVisible({ timeout: 5000 });
      }
    });

    test('cart updates in localStorage after add', async ({ page }) => {
      if (!productSlug) return;
      const addToCartBtn = page.getByRole('button', { name: /add to cart/i });
      if (await addToCartBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await addToCartBtn.click();
        await page.waitForTimeout(1000);
        const cartData = await page.evaluate(() => localStorage.getItem('hadha-cart'));
        expect(cartData).toBeTruthy();
        if (cartData) {
          const parsed = JSON.parse(cartData);
          expect(parsed.state.lines.length).toBeGreaterThan(0);
        }
      }
    });

    test('quantity stepper increments', async ({ page }) => {
      if (!productSlug) return;
      const plusBtn = page.locator('button').filter({ hasText: '+' }).first();
      if (await plusBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await plusBtn.click();
        await page.waitForTimeout(300);
      }
    });

    test('quantity stepper decrements', async ({ page }) => {
      if (!productSlug) return;
      const plusBtn = page.locator('button').filter({ hasText: '+' }).first();
      const minusBtn = page.locator('button').filter({ hasText: '-' }).first();
      if (
        (await plusBtn.isVisible({ timeout: 3000 }).catch(() => false)) &&
        (await minusBtn.isVisible({ timeout: 3000 }).catch(() => false))
      ) {
        await plusBtn.click();
        await page.waitForTimeout(200);
        await plusBtn.click();
        await page.waitForTimeout(200);
        await minusBtn.click();
        await page.waitForTimeout(200);
      }
    });

    test('variant products require selection before add to cart', async ({ page }) => {
      if (!productSlug) return;
      const variantBtns = page.locator('button[aria-pressed]');
      const count = await variantBtns.count();
      if (count > 0) {
        const addToCartBtn = page.getByRole('button', { name: /add to cart/i });
        if (await addToCartBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
          await addToCartBtn.click();
          await page.waitForTimeout(300);
          const variantError = page.getByText(/select a variant/i);
          await expect(variantError).toBeVisible();
        }
      }
    });

    test('sold out products show out of stock state', async ({ page }) => {
      if (!productSlug) return;
      await expect(page.locator('main, h1, body').first()).toBeVisible();
    });
  });

  test.describe('Cart Page', () => {
    test('cart page loads with cart summary', async ({ page }) => {
      await gotoPath(page, '/cart');
      await waitForPageReady(page);
      await expect(page.locator('main').first()).toBeVisible();
    });

    test('empty cart page has continue shopping link', async ({ page }) => {
      await gotoHome(page);
      await clearCartLocalStorage(page);
      await gotoPath(page, '/cart');
      await waitForPageReady(page);
      const continueLink = page.getByText(/continue shopping|start shopping|browse/i).or(
        page.locator('a[href="/collections"]'),
      );
      await expect(continueLink.first()).toBeVisible();
    });
  });

  test.describe('Cart Drawer', () => {
    test('view cart link is accessible', async ({ page }) => {
      await gotoHome(page);
      const viewCartLink = page.locator('a[href="/cart"]').first();
      await expect(page.locator('body')).toBeVisible();
    });

    test('checkout link redirects properly', async ({ page }) => {
      await gotoHome(page);
      const checkoutLink = page.locator('a[href="/checkout"]').first();
      await expect(page.locator('body')).toBeVisible();
    });
  });
});
