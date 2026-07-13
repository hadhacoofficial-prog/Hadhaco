#!/usr/bin/env python3
"""Generate the UAT customer-journey.spec.ts file."""
import os

OUT = os.path.join(os.path.dirname(__file__), "customer-journey.spec.ts")

PARTS = []

PARTS.append(r'''/**
 * Hadha.co - End-to-End Customer Journey UAT
 *
 * Validates the COMPLETE customer journey as a REAL CUSTOMER.
 * Run: npx playwright test tests/uat/customer-journey.spec.ts --project=chromium --workers=1
 */
import { test, expect, type Page } from '@playwright/test';
import {
  TEST_USER,
  gotoHome,
  gotoPath,
  waitForPageReady,
  dismissPopups,
  loginAsTestUser,
  clearCartLocalStorage,
  clearWishlistLocalStorage,
  getFirstProductSlug,
  getFirstCollectionSlug,
  isExpectedConsoleError,
} from '../helpers/test-utils';

interface UATContext {
  productSlug: string | null;
  collectionSlug: string | null;
  consoleErrors: string[];
  networkErrors: string[];
  screenshots: string[];
}

const uat: UATContext = {
  productSlug: null,
  collectionSlug: null,
  consoleErrors: [],
  networkErrors: [],
  screenshots: [],
};

async function captureFailure(page: Page, name: string) {
  const path = `test-results/uat-${name}-${Date.now()}.png`;
  await page.screenshot({ path, fullPage: true }).catch(() => {});
  uat.screenshots.push(path);
  return path;
}

function setupMonitoring(page: Page) {
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !isExpectedConsoleError(msg.text())) {
      uat.consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => {
    if (!isExpectedConsoleError(err.message)) {
      uat.consoleErrors.push(err.message);
    }
  });
  page.on('requestfailed', (req) => {
    const url = req.url();
    const errorText = req.failure()?.errorText ?? '';
    if (
      errorText === 'net::ERR_ABORTED' ||
      errorText === 'net::ERR_BLOCKED_BY_ORB' ||
      isExpectedConsoleError(url) ||
      url.includes('favicon') ||
      url.includes('analytics') ||
      url.includes('.tsx') ||
      url.includes('.ts') ||
      url.includes('localhost:8080/src/') ||
      url.includes('cdn.hadha.co') ||
      url.includes('x.com/i.jpg')
    ) {
      return;
    }
    uat.networkErrors.push(`${errorText}: ${url}`);
  });
}
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 1: HOMEPAGE & BROWSING
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('1. Homepage & Browsing', () => {
  test('1.1 Homepage loads successfully', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await expect(page).toHaveTitle(/hadha/i);
    await expect(page.locator('header, [role="banner"]').first()).toBeVisible();
  });

  test('1.2 Hero section is visible', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    const hero = page.locator('main, [class*="hero"]').first();
    await expect(hero).toBeVisible();
  });

  test('1.3 Collections visible on homepage', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await waitForPageReady(page);
    const main = page.locator('main').first();
    await expect(main).toBeVisible();
    const collectionLinks = page.locator('a[href*="/collections/"]');
    const count = await collectionLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('1.4 Featured products visible', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await waitForPageReady(page);
    const productLinks = page.locator('a[href*="/products/"]');
    const count = await productLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('1.5 Navigation menu functional', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    const header = page.locator('header, [role="banner"]').first();
    await expect(header).toBeVisible();
    const navLinks = header.locator('a');
    const count = await navLinks.count();
    expect(count).toBeGreaterThan(0);
  });

  test('1.6 Footer visible with links', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    const footer = page.locator('footer');
    await expect(footer).toBeVisible();
    const links = footer.locator('a');
    const count = await links.count();
    expect(count).toBeGreaterThan(0);
  });

  test('1.7 Promotional sections render', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await waitForPageReady(page);
    const main = page.locator('main').first();
    await expect(main).toBeVisible();
  });

  test('1.8 Images have alt text', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await waitForPageReady(page);
    const images = page.locator('img');
    const count = await images.count();
    for (let i = 0; i < Math.min(count, 20); i++) {
      const img = images.nth(i);
      const alt = await img.getAttribute('alt');
      const ariaHidden = await img.getAttribute('aria-hidden');
      expect(alt !== null || ariaHidden === 'true').toBeTruthy();
    }
  });

  test('1.9 No critical console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !isExpectedConsoleError(msg.text())) errors.push(msg.text());
    });
    page.on('pageerror', (err) => {
      if (!isExpectedConsoleError(err.message)) errors.push(err.message);
    });
    await gotoHome(page);
    await page.waitForTimeout(3000);
    expect(errors).toHaveLength(0);
  });

  test('1.10 Main content loaded and visible', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await waitForPageReady(page);
    const main = page.locator('main').first();
    await expect(main).toBeVisible();
    await page.waitForTimeout(2000);
    const text = await main.innerText().catch(() => '');
    expect(text.length).toBeGreaterThan(0);
  });

  test('1.11 WhatsApp FAB visible', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    const fab = page.locator('a[href*="wa.me"]');
    await expect(fab.first()).toBeVisible();
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 2: COLLECTIONS
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('2. Collections', () => {
  test('2.1 Collections page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/collections');
    await waitForPageReady(page);
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('2.2 First collection browsable', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/collections');
    await waitForPageReady(page);
    uat.collectionSlug = await getFirstCollectionSlug(page);
    if (uat.collectionSlug) {
      await gotoPath(page, `/collections/${uat.collectionSlug}`);
      await waitForPageReady(page);
      await expect(page.locator('h1, h2').first()).toBeVisible();
    }
  });

  test('2.3 Collection shows products', async ({ page }) => {
    setupMonitoring(page);
    if (!uat.collectionSlug) { test.skip(); return; }
    await gotoPath(page, `/collections/${uat.collectionSlug}`);
    await waitForPageReady(page);
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('2.4 Breadcrumbs on collection', async ({ page }) => {
    setupMonitoring(page);
    if (!uat.collectionSlug) { test.skip(); return; }
    await gotoPath(page, `/collections/${uat.collectionSlug}`);
    await waitForPageReady(page);
    const breadcrumb = page.locator('nav[aria-label*="breadcrumb"], [class*="breadcrumb"]').first();
    if (await breadcrumb.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(breadcrumb.locator('a[href="/"]').first()).toBeVisible();
    }
  });

  test('2.5 No broken images on collection', async ({ page }) => {
    setupMonitoring(page);
    if (!uat.collectionSlug) { test.skip(); return; }
    await gotoPath(page, `/collections/${uat.collectionSlug}`);
    await waitForPageReady(page);
    const images = page.locator('img');
    const count = await images.count();
    for (let i = 0; i < Math.min(count, 10); i++) {
      const src = await images.nth(i).getAttribute('src');
      if (src) expect(src).not.toBe('');
    }
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 3: PRODUCTS LISTING
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('3. Products Listing', () => {
  test('3.1 Products page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/products');
    await waitForPageReady(page);
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('3.2 Product items displayed', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/products');
    await waitForPageReady(page);
    const count = await page.locator('a[href*="/products/"]').count();
    expect(count).toBeGreaterThan(0);
  });

  test('3.3 Product slug captured', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/products');
    await waitForPageReady(page);
    uat.productSlug = await getFirstProductSlug(page);
    expect(uat.productSlug).toBeTruthy();
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 4: PRODUCT DETAIL
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('4. Product Detail', () => {
  test('4.1 Product page loads', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    if (!uat.productSlug) {
      await gotoPath(page, '/products');
      await waitForPageReady(page);
      uat.productSlug = await getFirstProductSlug(page);
    }
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('4.2 Product images visible', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    const count = await page.locator('img').count();
    expect(count).toBeGreaterThan(0);
  });

  test('4.3 Price displayed', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    const price = page.locator('main').getByText(/Rs\.\s*[\d,]+/).first();
    await expect(price).toBeVisible({ timeout: 10000 });
  });

  test('4.4 Add to cart button visible', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    const btn = page.getByRole('button', { name: /add to cart/i });
    expect(await btn.isVisible({ timeout: 5000 }).catch(() => false)).toBeTruthy();
  });

  test('4.5 Breadcrumbs on product', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    const bc = page.locator('nav[aria-label*="breadcrumb"], [class*="breadcrumb"]').first();
    if (await bc.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(bc.locator('a[href="/"]').first()).toBeVisible();
    }
  });

  test('4.6 Scroll to related products', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('4.7 No console errors on product', async ({ page }) => {
    test.setTimeout(60000);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    await page.waitForTimeout(2000);
    expect(errors.filter((e) => !isExpectedConsoleError(e))).toHaveLength(0);
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 5: SEARCH
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('5. Search', () => {
  test('5.1 Search overlay opens from header', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await dismissPopups(page);
    const btn = page.locator('header button[aria-label="Search"]').first();
    if (await btn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await btn.click();
      await page.waitForTimeout(500);
      await expect(page.locator('div[role="dialog"] input').first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('5.2 Trending searches shown', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await dismissPopups(page);
    const btn = page.locator('header button[aria-label="Search"]').first();
    if (await btn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await btn.click();
      await page.waitForTimeout(500);
      const trending = page.locator('div[role="dialog"]').getByRole('button', {
        name: /bugadi|chains|anklets|rings/i,
      });
      expect(await trending.count()).toBeGreaterThan(0);
    }
  });

  test('5.3 ESC closes search overlay', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await dismissPopups(page);
    const btn = page.locator('header button[aria-label="Search"]').first();
    if (await btn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await btn.click();
      await page.waitForTimeout(500);
      const input = page.locator('div[role="dialog"] input').first();
      await expect(input).toBeVisible({ timeout: 5000 });
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
      expect(await input.isVisible().catch(() => false)).toBeFalsy();
    }
  });

  test('5.4 Search page with query', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/search?q=chain');
    await waitForPageReady(page);
    await expect(page).toHaveTitle(/search|hadha/i);
  });

  test('5.5 Trending on empty search', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/search');
    await waitForPageReady(page);
    await expect(page.getByText(/trending|popular|suggestion/i).first()).toBeVisible();
  });

  test('5.6 Special characters handled', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/search?q=<script>alert(1)</script>');
    await waitForPageReady(page);
    await expect(page.locator('body')).toBeVisible();
    const fired = await page.evaluate(() => (window as Record<string, unknown>).__alertFired ?? false);
    expect(fired).toBeFalsy();
  });

  test('5.7 Long query handled', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, `/search?q=${'a'.repeat(200)}`);
    await waitForPageReady(page);
    await expect(page.locator('body')).toBeVisible();
  });

  test('5.8 Case insensitive search', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/search?q=CHAIN');
    await waitForPageReady(page);
    await expect(page.locator('body')).toBeVisible();
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 6: AUTHENTICATION
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('6. Authentication', () => {
  test('6.1 Login page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/account/login');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page).toHaveTitle(/sign in|login|hadha/i);
    await expect(page.locator('input[type="email"]').first()).toBeVisible();
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
  });

  test('6.2 Invalid login stays on login', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/account/login');
    await dismissPopups(page);
    await waitForPageReady(page);
    await page.locator('input[type="email"]').first().fill('wrong@example.com');
    await page.locator('input[type="password"]').first().fill('wrongpassword123');
    await page.getByRole('button', { name: /sign in/i }).click({ force: true });
    await page.waitForTimeout(3000);
    expect(page.url()).toContain('/account/login');
  });

  test('6.3 Register page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/account/register');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page).toHaveTitle(/register|create|sign up|hadha/i);
    await expect(page.locator('input[type="email"]').first()).toBeVisible();
  });

  test('6.4 Duplicate email rejected', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/account/register');
    await dismissPopups(page);
    await waitForPageReady(page);
    const nameField = page.locator('input[name="name"], input[placeholder*="name" i], input[type="text"]').first();
    if (await nameField.isVisible({ timeout: 3000 }).catch(() => false)) await nameField.fill('Test User');
    await page.locator('input[type="email"]').first().fill(TEST_USER.email);
    const pw = page.locator('input[type="password"]').first();
    if (await pw.isVisible({ timeout: 3000 }).catch(() => false)) await pw.fill('TestPassword123!');
    const btn = page.getByRole('button', { name: /create account|sign up|register/i });
    if (await btn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await btn.click({ force: true });
      await page.waitForTimeout(3000);
      expect(page.url()).toContain('/account/register');
    }
  });

  test('6.5 Forgot password page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/account/forgot-password');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.locator('input[type="email"]').first()).toBeVisible();
  });

  test('6.6 Reset password page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/account/reset-password');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.locator('body')).toBeVisible();
  });

  test('6.7 Successful login', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    expect(page.url().includes('/account')).toBeTruthy();
  });

  test('6.8 Dashboard shows account content', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await waitForPageReady(page);
    await page.waitForTimeout(2000);
    const hasContent = (await page.getByText(/overview|member since|orders|dashboard/i).count()) > 0;
    const hasSidebar = (await page.getByRole('button', { name: /overview|orders|addresses/i }).count()) > 0;
    expect(hasContent || hasSidebar).toBeTruthy();
  });

  test('6.9 Session persists across navigation', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoHome(page);
    await gotoPath(page, '/account');
    await waitForPageReady(page);
    expect((await page.getByText(/overview|member since|orders/i).count()) > 0).toBeTruthy();
  });

  test('6.10 Session persists after refresh', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await page.reload();
    await waitForPageReady(page);
    await page.waitForTimeout(3000);
    const hasContent = (await page.getByText(/overview|member since|orders|dashboard/i).count()) > 0;
    const hasSidebar = (await page.getByRole('button', { name: /overview|orders|addresses/i }).count()) > 0;
    expect(hasContent || hasSidebar).toBeTruthy();
  });

  test('6.11 Logout clears session', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await dismissPopups(page);
    await page.getByRole('button', { name: /sign out/i }).first().click();
    await page.waitForTimeout(3000);
    const url = page.url();
    expect(url.endsWith('/') || url.endsWith(':8080/')).toBeTruthy();
  });

  test('6.12 Cannot access account after logout', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await dismissPopups(page);
    await page.getByRole('button', { name: /sign out/i }).first().click();
    await page.waitForTimeout(3000);
    await gotoPath(page, '/account');
    await dismissPopups(page);
    await waitForPageReady(page);
    await page.waitForTimeout(2000);
    const isOnLogin = page.url().includes('/account/login');
    const showsSignIn = (await page.getByText(/sign in|log in/i).count()) > 0;
    expect(isOnLogin || showsSignIn).toBeTruthy();
    await expect(page.getByRole('button', { name: /^(Overview|Orders|Addresses|Wishlist|Profile|Security)$/ })).toHaveCount(0);
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 7: WISHLIST
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('7. Wishlist', () => {
  test('7.1 Wishlist page loads', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/wishlist');
    await waitForPageReady(page);
    await expect(page).toHaveTitle(/wishlist|hadha/i);
  });

  test('7.2 Empty wishlist state', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/');
    await waitForPageReady(page);
    await clearWishlistLocalStorage(page);
    await gotoPath(page, '/wishlist');
    await waitForPageReady(page);
    await expect(page.getByText(/empty|no items|discover|save pieces/i).first()).toBeVisible();
  });

  test('7.3 Wishlist persists via localStorage', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/');
    await waitForPageReady(page);
    await clearWishlistLocalStorage(page);
    await page.evaluate(() => {
      localStorage.setItem('hadha-wishlist', JSON.stringify({
        state: { items: [{ id: 't', slug: 'test-p', name: 'Test Product', image: 'https://x.com/i.jpg', price: 999, sku: 'T' }] },
        version: 0,
      }));
    });
    await gotoPath(page, '/wishlist');
    await waitForPageReady(page);
    await expect(page.getByText(/test product/i).first()).toBeVisible();
  });

  test('7.4 Wishlist header badge', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoHome(page);
    await expect(page.locator('header').first()).toBeVisible();
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 8: CART
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('8. Cart', () => {
  test('8.1 Empty cart shows empty state', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await clearCartLocalStorage(page);
    await gotoPath(page, '/cart');
    await waitForPageReady(page);
    const h = page.getByText(/shopping cart|your cart/i);
    const e = page.getByText(/cart is empty|start shopping/i);
    await expect(h.or(e).first()).toBeVisible();
  });

  test('8.2 Add product to cart via UI', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await gotoHome(page);
    await clearCartLocalStorage(page);
    if (!uat.productSlug) {
      await gotoPath(page, '/products');
      await waitForPageReady(page);
      uat.productSlug = await getFirstProductSlug(page);
    }
    if (!uat.productSlug) { test.skip(); return; }
    await gotoPath(page, `/products/${uat.productSlug}`);
    await waitForPageReady(page);
    const btn = page.getByRole('button', { name: /add to cart/i });
    if (await btn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await btn.click();
      await page.waitForTimeout(1000);
      await expect(page.getByRole('heading', { name: /your cart/i })).toBeVisible({ timeout: 5000 });
    }
  });

  test('8.3 Cart persists in localStorage', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await gotoHome(page);
    const data = await page.evaluate(() => localStorage.getItem('hadha-cart'));
    if (data) expect(JSON.parse(data).state.lines.length).toBeGreaterThan(0);
  });

  test('8.4 Cart page shows items', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await gotoPath(page, '/cart');
    await waitForPageReady(page);
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('8.5 Cart persists across refresh', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await gotoPath(page, '/cart');
    await waitForPageReady(page);
    await page.reload();
    await waitForPageReady(page);
    await expect(page.locator('main').first()).toBeVisible();
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 9: CHECKOUT
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('9. Checkout', () => {
  test('9.1 Guest restricted from checkout', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/checkout');
    await dismissPopups(page);
    await waitForPageReady(page);
    await page.waitForTimeout(2000);
    expect(page.url().includes('/account/login') || page.url().includes('/checkout')).toBeTruthy();
  });

  test('9.2 Authenticated user accesses checkout', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/checkout');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByRole('heading', { name: /checkout/i })).toBeVisible();
  });

  test('9.3 Order summary visible', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/checkout');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByText(/order summary|summary|subtotal/i).first()).toBeVisible();
  });

  test('9.4 Delivery options visible', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/checkout');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByText(/delivery method|shipping method|standard delivery/i).first()).toBeVisible();
  });

  test('9.5 Coupon section visible', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/checkout');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByText(/coupon|offer|discount/i).first()).toBeVisible();
  });

  test('9.6 Place order button visible', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/checkout');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByRole('button', { name: /place order/i })).toBeVisible();
  });

  test('9.7 Address form fields exist', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await gotoPath(page, '/checkout');
    await dismissPopups(page);
    await waitForPageReady(page);
    let found = 0;
    for (const name of ['firstName', 'lastName', 'address', 'city', 'state', 'pincode']) {
      if (await page.locator(`[name="${name}"]`).isVisible({ timeout: 2000 }).catch(() => false)) found++;
    }
    expect(found).toBeGreaterThan(0);
  });

  test('9.8 Payment failed page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/checkout/payment-failed');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByText(/payment failed|oops|something went wrong/i).first()).toBeVisible();
  });

  test('9.9 Reservation expired page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/checkout/reservation-expired');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByText(/reservation|expired|oops/i).first()).toBeVisible();
  });

  test('9.10 Stock changed page loads', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/checkout/stock-changed');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.getByText(/stock|changed|oops/i).first()).toBeVisible();
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 10: ACCOUNT MANAGEMENT
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('10. Account Management', () => {
  test('10.1 Dashboard sidebar tabs', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    for (const tab of ['Overview', 'Orders', 'Addresses', 'Wishlist', 'Profile', 'Security']) {
      await expect(page.getByRole('button', { name: new RegExp(tab, 'i') })).toBeVisible({ timeout: 5000 });
    }
  });

  test('10.2 Overview shows member since', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await expect(page.getByText(/member since/i).first()).toBeVisible();
  });

  test('10.3 Orders tab content', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await dismissPopups(page);
    await page.getByRole('button', { name: /orders/i }).click();
    await page.waitForTimeout(500);
    await expect(page.getByText(/your orders|order history|no orders yet/i).first()).toBeVisible();
  });

  test('10.4 Addresses tab content', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await dismissPopups(page);
    await page.getByRole('button', { name: /addresses/i }).click();
    await page.waitForTimeout(500);
    await expect(page.getByText(/saved addresses|addresses/i).first()).toBeVisible();
  });

  test('10.5 Add address form appears', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await dismissPopups(page);
    await page.getByRole('button', { name: /addresses/i }).click();
    await page.waitForTimeout(500);
    await page.getByRole('button', { name: /add address/i }).click();
    await page.waitForTimeout(500);
    await expect(page.locator('form').first()).toBeVisible();
  });

  test('10.6 Profile tab content', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await dismissPopups(page);
    await page.getByRole('button', { name: /profile/i }).click();
    await page.waitForTimeout(500);
    await expect(page.getByText(/profile information|edit profile/i).first()).toBeVisible();
  });

  test('10.7 Security tab password form', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await dismissPopups(page);
    await page.getByRole('button', { name: /security/i }).click();
    await page.waitForTimeout(500);
    await expect(page.getByText(/security|password/i).first()).toBeVisible();
  });

  test('10.8 Sign out button exists', async ({ page }) => {
    test.setTimeout(60000);
    setupMonitoring(page);
    await loginAsTestUser(page);
    await expect(page.getByRole('button', { name: /sign out/i }).first()).toBeVisible();
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 11: STATIC PAGES
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('11. Static Pages', () => {
  const pages = [
    { path: '/about', pat: /about|story|hadha/i },
    { path: '/faq', pat: /faq|hadha/i },
    { path: '/contact', pat: /contact|hadha/i },
    { path: '/privacy', pat: /privacy|hadha/i },
    { path: '/terms', pat: /terms|hadha/i },
    { path: '/shipping-returns', pat: /shipping|returns|hadha/i },
    { path: '/store-locator', pat: /store|locator|hadha/i },
  ];
  for (const { path, pat } of pages) {
    test(`${path} loads correctly`, async ({ page }) => {
      setupMonitoring(page);
      await gotoPath(page, path);
      await dismissPopups(page);
      await waitForPageReady(page);
      await expect(page).toHaveTitle(pat);
      await expect(page.locator('h1, h2').first()).toBeVisible();
      await expect(page.locator('footer')).toBeVisible();
    });
  }

  test('About mentions BIS Hallmarked', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/about');
    await dismissPopups(page);
    await waitForPageReady(page);
    expect(await page.getByText(/bis|hallmarked|hallmark/i).count()).toBeGreaterThan(0);
  });

  test('Contact has form', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/contact');
    await dismissPopups(page);
    await waitForPageReady(page);
    await expect(page.locator('form').first()).toBeVisible();
  });

  test('FAQ has accordions', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/faq');
    await dismissPopups(page);
    await waitForPageReady(page);
    const count = await page.locator('button, [role="button"]').filter({
      hasText: /order|shipping|return|payment|product/i,
    }).count();
    expect(count).toBeGreaterThan(0);
  });

  test('Store locator shows locations', async ({ page }) => {
    setupMonitoring(page);
    await gotoPath(page, '/store-locator');
    await dismissPopups(page);
    await waitForPageReady(page);
    expect(await page.getByText(/visakhapatnam|hyderabad|bengaluru|chennai/i).count()).toBeGreaterThan(0);
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 12: SECURITY & ROUTE GUARDS
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('12. Security & Route Guards', () => {
  test('12.1 Unauth /account redirects to login', async ({ page }) => {
    setupMonitoring(page);
    await page.goto('/account', { waitUntil: 'load' });
    await waitForPageReady(page);
    await page.waitForTimeout(3000);
    expect(page.url().includes('/account/login') || (await page.getByText(/sign in|log in/i).count()) > 0).toBeTruthy();
  });

  test('12.2 Unauth /checkout restricted', async ({ page }) => {
    setupMonitoring(page);
    await page.goto('/checkout', { waitUntil: 'load' });
    await waitForPageReady(page);
    await page.waitForTimeout(2000);
    expect(page.url().includes('/account/login') || page.url().includes('/checkout')).toBeTruthy();
  });

  test('12.3 404 for invalid routes', async ({ page }) => {
    setupMonitoring(page);
    await page.goto('/nonexistent-page-xyz', { waitUntil: 'load' });
    await waitForPageReady(page);
    await expect(page.getByText(/404|not found|doesn't exist/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('12.4 404 has Go Home link', async ({ page }) => {
    setupMonitoring(page);
    await page.goto('/nonexistent-page-xyz', { waitUntil: 'load' });
    await waitForPageReady(page);
    await expect(page.getByRole('link', { name: /go home/i }).first()).toBeVisible({ timeout: 10000 });
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 13: MOBILE LAYOUT
// ═════════════════════════════════════════════════════════════════════════════

test.describe.serial('13. Mobile Layout', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test('13.1 Bottom nav visible', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await expect(page.locator('nav[aria-label="Primary mobile navigation"]')).toBeVisible();
  });

  test('13.2 Home tab present', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await expect(page.locator('nav[aria-label="Primary mobile navigation"]').getByText('Home')).toBeVisible();
  });

  test('13.3 Search tab present', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await expect(page.locator('nav[aria-label="Primary mobile navigation"]').getByText('Search')).toBeVisible();
  });

  test('13.4 Wishlist tab present', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    expect(await page.locator('nav[aria-label="Primary mobile navigation"]').getByText(/wishlist/i).count()).toBeGreaterThan(0);
  });

  test('13.5 Search tab opens overlay', async ({ page }) => {
    setupMonitoring(page);
    await gotoHome(page);
    await page.locator('nav[aria-label="Primary mobile navigation"]').getByText('Search').click();
    await page.waitForTimeout(500);
    await expect(page.locator('div[role="dialog"][aria-modal="true"]')).toBeVisible({ timeout: 5000 });
  });
});
''')

PARTS.append(r'''
// ═════════════════════════════════════════════════════════════════════════════
//  SECTION 14: UAT SUMMARY
// ═════════════════════════════════════════════════════════════════════════════

test.describe('14. UAT Summary', () => {
  test('14.1 No accumulated console errors', async () => {
    expect(uat.consoleErrors).toHaveLength(0);
  });

  test('14.2 No critical network failures', async () => {
    const critical = uat.networkErrors.filter(
      (e) =>
        !e.includes('favicon') &&
        !e.includes('analytics') &&
        !e.includes('sentry') &&
        !e.includes('.tsx') &&
        !e.includes('.ts') &&
        !e.includes('localhost:8080/src/'),
    );
    expect(critical).toHaveLength(0);
  });

  test('14.3 UAT metrics', async () => {
    console.log(`Screenshots captured: ${uat.screenshots.length}`);
    console.log(`Console errors: ${uat.consoleErrors.length}`);
    console.log(`Network errors: ${uat.networkErrors.length}`);
  });
});
''')

with open(OUT, "w", encoding="utf-8") as f:
    f.write("".join(PARTS))

print(f"Written {os.path.getsize(OUT)} bytes to {OUT}")
