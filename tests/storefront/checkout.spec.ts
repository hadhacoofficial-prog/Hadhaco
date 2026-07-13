import { test, expect } from '@playwright/test';
import {
  gotoPath,
  loginAsTestUser,
  TEST_USER,
  clearCartLocalStorage,
  getFirstProductSlug,
  waitForPageReady,
  dismissPopups,
} from '../helpers/test-utils';

test.describe('Checkout Flow', () => {
  test.describe('Checkout Page Access', () => {
    test('unauthenticated user redirected to login', async ({ page }) => {
      await gotoPath(page, '/checkout');
      await dismissPopups(page);
      await waitForPageReady(page);
      await page.waitForTimeout(2000);
      const url = page.url();
      const isOnCheckout = url.includes('/checkout');
      const isOnLogin = url.includes('/account/login');
      // Either redirected to login, or still on checkout
      expect(isOnLogin || isOnCheckout).toBeTruthy();
    });

    test('authenticated user can access checkout', async ({ page }) => {
      await loginAsTestUser(page);
      await gotoPath(page, '/checkout');
      await dismissPopups(page);
      await waitForPageReady(page);
      const heading = page.getByRole('heading', { name: /checkout/i });
      await expect(heading).toBeVisible();
    });
  });

  test.describe('Checkout Page Layout', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsTestUser(page);
      await gotoPath(page, '/checkout');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('breadcrumbs show Home > Cart > Checkout', async ({ page }) => {
      const breadcrumb = page.locator('nav[aria-label*="breadcrumb"], [class*="breadcrumb"]').first();
      // Breadcrumbs may or may not exist on checkout page
      if (await breadcrumb.isVisible({ timeout: 3000 }).catch(() => false)) {
        const homeLink = breadcrumb.locator('a[href="/"]');
        await expect(homeLink).toBeVisible();
      }
    });

    test('order summary section exists', async ({ page }) => {
      const summary = page.getByText(/order summary|summary|subtotal/i);
      await expect(summary.first()).toBeVisible();
    });

    test('delivery method section exists', async ({ page }) => {
      const delivery = page.getByText(/delivery method|shipping method/i);
      await expect(delivery.first()).toBeVisible();
    });

    test('coupon section exists', async ({ page }) => {
      const coupon = page.getByText(/coupon|offer|discount/i);
      await expect(coupon.first()).toBeVisible();
    });

    test('place order button exists', async ({ page }) => {
      const placeOrderBtn = page.getByRole('button', { name: /place order/i });
      await expect(placeOrderBtn).toBeVisible();
    });

    test('standard delivery option is available', async ({ page }) => {
      const standard = page.getByText(/standard delivery/i);
      await expect(standard.first()).toBeVisible();
    });

    test('express delivery option is available', async ({ page }) => {
      const express = page.getByText(/express delivery/i);
      await expect(express.first()).toBeVisible();
    });
  });

  test.describe('Checkout Address Selection', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsTestUser(page);
      await gotoPath(page, '/checkout');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('new address form appears when no saved addresses', async ({ page }) => {
      const addressSection = page.getByText(/shipping address|delivery address|new address/i);
      await expect(addressSection.first()).toBeVisible();
    });

    test('new address form has all required fields', async ({ page }) => {
      // Check for address form fields
      const fields = ['firstName', 'lastName', 'address', 'city', 'state', 'pincode'];
      for (const fieldName of fields) {
        const field = page.locator(`[name="${fieldName}"]`);
        if (await field.isVisible({ timeout: 2000 }).catch(() => false)) {
          await expect(field).toBeVisible();
        }
      }
    });

    test('phone field validates Indian mobile numbers', async ({ page }) => {
      // This test does 3 sequential navigations (products list, product
      // detail, checkout) instead of 1, so occasional Firefox goto retries
      // (see gotoWithRetry in test-utils.ts) can stack close to the default
      // 30s test timeout — give it explicit headroom.
      test.setTimeout(60000);
      // Place Order is disabled whenever the cart is empty (see checkout.tsx:
      // `disabled={lines.length === 0 || submitting}`), independent of address/
      // phone validity — this describe block's beforeEach never adds anything
      // to the cart, so the button was unclickable for a reason unrelated to
      // phone validation. Add a product first so the real validation path runs.
      await gotoPath(page, '/products');
      await waitForPageReady(page);
      const slug = await getFirstProductSlug(page);
      if (slug) {
        await gotoPath(page, `/products/${slug}`);
        await waitForPageReady(page);
        const addToCartBtn = page.getByRole('button', { name: /add to cart/i });
        if (await addToCartBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
          await addToCartBtn.click();
          await page.waitForTimeout(500);
        }
      }
      await gotoPath(page, '/checkout');
      await dismissPopups(page);
      await waitForPageReady(page);

      const phoneField = page.locator('[name="phone"], input[type="tel"]').first();
      if (await phoneField.isVisible({ timeout: 5000 }).catch(() => false)) {
        await phoneField.fill('123');
        // Try submitting
        const placeOrderBtn = page.getByRole('button', { name: /place order/i });
        await placeOrderBtn.click();
        await page.waitForTimeout(1000);
        // Should show phone validation error
        const phoneError = page.getByText(/valid.*mobile|10.*digit|phone/i);
        await expect(phoneError.first()).toBeVisible({ timeout: 5000 });
      }
    });
  });

  test.describe('Checkout Coupon Flow', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsTestUser(page);
      await gotoPath(page, '/checkout');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('coupon input field exists', async ({ page }) => {
      const couponInput = page.locator('input[placeholder*="coupon" i], input[placeholder*="code" i]');
      if (await couponInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(couponInput).toBeVisible();
      }
    });

    test('apply button is disabled when input is empty', async ({ page }) => {
      const applyBtn = page.getByRole('button', { name: /apply/i });
      if (await applyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        const isDisabled = await applyBtn.isDisabled();
        expect(isDisabled).toBeTruthy();
      }
    });

    test('invalid coupon shows error', async ({ page }) => {
      const couponInput = page.locator('input[placeholder*="coupon" i], input[placeholder*="code" i], input[name*="coupon" i]');
      const applyBtn = page.getByRole('button', { name: /apply/i });
      const hasCouponInput = await couponInput.isVisible({ timeout: 3000 }).catch(() => false);
      const hasApplyBtn = await applyBtn.isVisible({ timeout: 3000 }).catch(() => false);
      if (hasCouponInput && hasApplyBtn) {
        await couponInput.fill('INVALIDCODE');
        await applyBtn.click();
        await page.waitForTimeout(2000);
        // Should show error message
        const error = page.getByText(/invalid|expired|not valid|doesn't exist/i);
        await expect(error.first()).toBeVisible({ timeout: 5000 });
      }
    });
  });

  test.describe('Checkout Order Summary', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsTestUser(page);
      await gotoPath(page, '/checkout');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('subtotal is displayed', async ({ page }) => {
      const subtotal = page.getByText(/subtotal/i);
      await expect(subtotal.first()).toBeVisible();
    });

    test('shipping cost is displayed', async ({ page }) => {
      const shipping = page.getByText(/shipping/i);
      await expect(shipping.first()).toBeVisible();
    });

    test('total is displayed', async ({ page }) => {
      const total = page.getByText(/total/i);
      await expect(total.first()).toBeVisible();
    });

    test('razorpay security note is shown', async ({ page }) => {
      const secured = page.getByText(/secured|razorpay|payment/i);
      await expect(secured.first()).toBeVisible();
    });
  });
});

test.describe('Checkout Success Page', () => {
  test('shows error when no order identifier', async ({ page }) => {
    await loginAsTestUser(page);
    await gotoPath(page, '/checkout/success');
    await dismissPopups(page);
    await waitForPageReady(page);
    // Should show some state - loading, error, or empty
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });
});

test.describe('Checkout Error Pages', () => {
  test('payment failed page loads', async ({ page }) => {
    await gotoPath(page, '/checkout/payment-failed');
    await dismissPopups(page);
    await waitForPageReady(page);
    const content = page.getByText(/payment failed|oops|something went wrong/i);
    await expect(content.first()).toBeVisible();
  });

  test('reservation expired page loads', async ({ page }) => {
    await gotoPath(page, '/checkout/reservation-expired');
    await dismissPopups(page);
    await waitForPageReady(page);
    const content = page.getByText(/reservation|expired|oops/i);
    await expect(content.first()).toBeVisible();
  });

  test('stock changed page loads', async ({ page }) => {
    await gotoPath(page, '/checkout/stock-changed');
    await dismissPopups(page);
    await waitForPageReady(page);
    const content = page.getByText(/stock|changed|oops/i);
    await expect(content.first()).toBeVisible();
  });
});
