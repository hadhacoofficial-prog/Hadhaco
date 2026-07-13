import { type Page, type Locator, expect } from '@playwright/test';

export const TEST_USER = {
  email: process.env.TEST_USER_EMAIL ?? 'testcustomer@hadha.co',
  password: process.env.TEST_USER_PASSWORD ?? 'TestPassword123!',
  name: 'Test Customer',
};

export const STOREFRONT_URL = process.env.BASE_URL ?? 'http://localhost:8080';

// Vite dev server's own URL-decode-normalization middleware 307s %3Cscript%3E-
// style paths back to their literal-character form, which the browser
// re-encodes — an infinite redirect loop that only exists under `vite dev`
// (confirmed: identical behavior for arbitrary static paths like
// /src/<foo>.tsx that never reach app/route code; does not happen in a
// production build). Each browser engine reports it with different text.
export function isKnownDevServerRedirectLoop(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return (
    err.message.includes('ERR_TOO_MANY_REDIRECTS') || // Chromium
    err.message.includes('NS_ERROR_REDIRECT_LOOP') || // Firefox
    err.message.includes('cannot follow more than') // WebKit
  );
}

// ── Navigation helpers ───────────────────────────────────────────────────────

export async function waitForPageReady(page: Page) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForLoadState('load', { timeout: 30000 }).catch(() => {});
  // SSR app: wait for header or body to have content
  await page.locator('header, nav, [role="banner"]').first()
    .waitFor({ state: 'visible', timeout: 15000 })
    .catch(() => {});
}

// Firefox occasionally aborts an in-flight page.goto() (observed as
// NS_BINDING_ABORTED, NS_ERROR_FAILURE, or "frame was detached" — the exact
// message varies) when this SSR app's client-side hydration/router kicks off
// a navigation-adjacent operation in the same tick. This is a known-transient
// Playwright/Firefox condition (not reproducible in Chromium or WebKit here);
// the officially recommended mitigation is to retry the navigation once
// rather than change waitUntil semantics (tried 'domcontentloaded' instead of
// 'load' first; it did not reduce the failure rate). Since the network-error
// message text isn't stable, retry on any goto failure rather than pattern-
// match specific strings. Observed as bursty rather than strictly one-off —
// a single retry sometimes still lands on the same transient condition — so
// this allows up to 3 attempts total with a short backoff.
async function gotoWithRetry(page: Page, url: string, options: Parameters<Page['goto']>[1]) {
  const attempts = 3;
  for (let i = 1; i <= attempts; i++) {
    try {
      await page.goto(url, options);
      return;
    } catch (err) {
      // The dev-server redirect loop (see isKnownDevServerRedirectLoop) is a
      // permanent, not transient, failure — retrying it 3x in a row was
      // observed to crash the Firefox page/context entirely rather than just
      // fail cleanly once.
      if (isKnownDevServerRedirectLoop(err) || i === attempts) throw err;
      await page.waitForTimeout(300);
    }
  }
}

// Pre-seeds the promotional welcome-popup's own "already seen" localStorage
// flag before any page script runs, so it never opens in the first place.
// No test in this suite exercises WelcomeOfferModal itself — it's purely an
// incidental obstacle other tests have to clear — and its 1200ms open-delay
// makes any close-it-after-the-fact approach an inherent timing race (see
// dismissPopups()'s own best-effort handling below, kept as a fallback for
// direct page.goto() calls that bypass these helpers). Preventing it from
// appearing at all is more reliable than racing to close it.
async function suppressWelcomePopup(page: Page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('hadha-welcome-offer-seen', '1');
    } catch {
      // ignore (private browsing / storage disabled)
    }
  });
}

export async function gotoHome(page: Page) {
  await suppressWelcomePopup(page);
  await gotoWithRetry(page, '/', { waitUntil: 'load' });
  await page.locator('header, nav, [role="banner"]').first()
    .waitFor({ state: 'visible', timeout: 15000 })
    .catch(() => {});
  await dismissPopups(page);
}

export async function gotoPath(page: Page, path: string) {
  await suppressWelcomePopup(page);
  await gotoWithRetry(page, path, { waitUntil: 'load', timeout: 30000 });
  await page.locator('header, nav, [role="banner"], main').first()
    .waitFor({ state: 'visible', timeout: 15000 })
    .catch(() => {});
  await dismissPopups(page);
}

// ── Overlay / popup helpers ──────────────────────────────────────────────────

export async function dismissPopups(page: Page) {
  // Deterministically wait for + close the promotional welcome popup
  // (src/components/common/WelcomeOfferModal.tsx, `div[role="dialog"]
  // [aria-modal="false"]`) if it's going to appear at all — it opens on a
  // 1200ms delay, so a short fire-and-forget check here would often finish
  // before the popup exists, let the caller proceed thinking there's nothing
  // to dismiss, and then have it open mid-test and block whatever's visually
  // underneath its (correctly click-through-proof) card. Explicitly waiting
  // for it to become hidden after clicking Close — rather than assuming the
  // click worked — avoids racing its close animation too.
  const welcomePopup = page.locator('div[role="dialog"][aria-modal="false"]').first();
  if (await welcomePopup.isVisible({ timeout: 1600 }).catch(() => false)) {
    await welcomePopup
      .getByRole('button', { name: /close/i })
      .first()
      .click({ force: true })
      .catch(() => {});
    await welcomePopup.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
  }

  const dismissAttempts = [
    // Try Close button with aria-label (covers other overlays, e.g. a search
    // overlay left open from a previous step).
    async () => {
      const btn = page.locator('button[aria-label="Close"]').first();
      if (await btn.isVisible({ timeout: 500 }).catch(() => false)) {
        await btn.click({ force: true });
        await page.waitForTimeout(400);
        return true;
      }
      return false;
    },
    // Try any button containing "Close" text
    async () => {
      const btn = page.getByRole('button', { name: /close/i }).first();
      if (await btn.isVisible({ timeout: 500 }).catch(() => false)) {
        await btn.click({ force: true });
        await page.waitForTimeout(400);
        return true;
      }
      return false;
    },
    // Try Escape key
    async () => {
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
      return true;
    },
    // Try clicking outside overlay (click at 10,10 on viewport)
    async () => {
      await page.mouse.click(10, 10);
      await page.waitForTimeout(300);
      return true;
    },
  ];
  for (const attempt of dismissAttempts) {
    try {
      if (await attempt()) break;
    } catch {
      // Ignore
    }
  }
}

// ── Console error helpers ────────────────────────────────────────────────────

export function isExpectedConsoleError(text: string): boolean {
  const ignored = [
    'favicon',
    'analytics',
    'gtag',
    '404',
    'sentry',
    'ERR_CONNECTION_REFUSED',
    'ERR_CONNECTION_TIMED_OUT',
    'net::ERR',
    'Failed to load resource',
    'hydrat',        // hydration warnings
    'ResizeObserver', // benign
    'WebSocket',
    'websocket',
    'Failed to fetch',
    'cannot contain a nested',  // React hydration warnings about nested elements
  ];
  return ignored.some((i) => text.toLowerCase().includes(i.toLowerCase()));
}

// ── Auth helpers ─────────────────────────────────────────────────────────────

export async function loginAsTestUser(page: Page) {
  await page.goto('/account/login', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await dismissPopups(page);
  await page.waitForSelector('input[type="email"]', { timeout: 15000 });
  await page.locator('input[type="email"]').first().fill(TEST_USER.email);
  await page.locator('input[type="password"]').first().fill(TEST_USER.password);
  const signInBtn = page.getByRole('button', { name: /sign in/i });
  await signInBtn.click();
  await page.waitForURL('**/account**', { timeout: 30000 }).catch(() => {});
  await waitForPageReady(page);
  await dismissPopups(page);
}

export async function logoutUser(page: Page) {
  await page.goto('/account', { waitUntil: 'load' });
  await waitForPageReady(page);
  const signOutBtn = page.getByRole('button', { name: /sign out/i });
  if (await signOutBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await signOutBtn.click();
    await page.waitForURL('**/', { timeout: 10000 });
  }
}

export async function isLoggedIn(page: Page): Promise<boolean> {
  await page.goto('/account', { waitUntil: 'load' });
  await waitForPageReady(page);
  return page.url().includes('/account') && !page.url().includes('/account/login');
}

// ── UI assertion helpers ─────────────────────────────────────────────────────

export async function expectVisible(locator: Locator) {
  await expect(locator).toBeVisible();
}

export async function expectHidden(locator: Locator) {
  await expect(locator).toBeHidden();
}

// ── Cart helpers ─────────────────────────────────────────────────────────────

export async function clearCartLocalStorage(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem('hadha-cart');
  });
}

export async function clearWishlistLocalStorage(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem('hadha-wishlist');
  });
}

export async function addProductToCartViaLocalStorage(
  page: Page,
  productId: string,
  quantity: number = 1,
) {
  await page.evaluate(
    ({ productId, quantity }) => {
      const cartKey = 'hadha-cart';
      const existing = JSON.parse(localStorage.getItem(cartKey) ?? '{}');
      const lines = existing?.state?.lines ?? [];
      const lineKey = `${productId}::`;
      const existingLine = lines.find((l: { productId: string; variantId?: string }) => {
        const key = `${l.productId}::${l.variantId ?? ''}`;
        return key === lineKey;
      });
      if (existingLine) {
        existingLine.qty += quantity;
      } else {
        lines.push({ productId, variantId: undefined, qty: quantity });
      }
      localStorage.setItem(cartKey, JSON.stringify({ state: { ...existing?.state, lines }, version: 0 }));
    },
    { productId, quantity },
  );
}

// ── Toast assertion helpers ──────────────────────────────────────────────────

export async function expectToast(page: Page, text: string, timeout = 10000) {
  const toast = page.locator('[data-sonner-toaster]').getByText(text);
  await expect(toast).toBeVisible({ timeout });
}

// ── Wait for data loading helpers ─────────────────────────────────────────────

export async function waitForProductsToLoad(page: Page) {
  await waitForPageReady(page);
  // Wait for product cards or skeletons to appear then disappear
  await page
    .locator('a[href*="/products/"], [class*="product-card"], [class*="ProductCard"]')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
    .catch(() => {});
}

export async function waitForNoSkeletons(page: Page) {
  const skeletons = page.locator('.animate-pulse, [data-skeleton]');
  const count = await skeletons.count();
  if (count > 0) {
    await page.waitForFunction(
      () => document.querySelectorAll('.animate-pulse, [data-skeleton]').length === 0,
      { timeout: 10000 },
    );
  }
}

// ── Intersection observer helpers ─────────────────────────────────────────────

export async function scrollToElement(page: Page, locator: Locator) {
  await locator.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
}

// ── Form helpers ─────────────────────────────────────────────────────────────

export async function fillAddressForm(
  page: Page,
  address: {
    firstName?: string;
    lastName?: string;
    phone?: string;
    address?: string;
    apt?: string;
    landmark?: string;
    city?: string;
    state?: string;
    pincode?: string;
  } = {},
) {
  const defaults = {
    firstName: 'Test',
    lastName: 'User',
    phone: '9876543210',
    address: '123 Test Street',
    apt: '',
    landmark: 'Near Test Park',
    city: 'Visakhapatnam',
    state: 'Andhra Pradesh',
    pincode: '530001',
  };
  const data = { ...defaults, ...address };

  const fields: Record<string, string> = {
    firstName: data.firstName,
    lastName: data.lastName,
    phone: data.phone,
    address: data.address,
    apt: data.apt,
    landmark: data.landmark,
    city: data.city,
    state: data.state,
    pincode: data.pincode,
  };

  for (const [name, value] of Object.entries(fields)) {
    const field = page.locator(`[name="${name}"]`);
    if (await field.isVisible({ timeout: 2000 }).catch(() => false)) {
      await field.fill(value);
    }
  }
}

// ── Product helpers ──────────────────────────────────────────────────────────

export async function getFirstProductSlug(page: Page): Promise<string | null> {
  try {
    const link = page.locator('a[href*="/products/"]').first();
    const href = await link.getAttribute('href', { timeout: 10000 });
    if (!href) return null;
    const match = href.match(/\/products\/([^/?]+)/);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

export async function getFirstCollectionSlug(page: Page): Promise<string | null> {
  const link = page.locator('a[href*="/collections/"]').first();
  const href = await link.getAttribute('href');
  if (!href) return null;
  const match = href.match(/\/collections\/([^/?]+)/);
  return match ? match[1] : null;
}

// ── Route paths ──────────────────────────────────────────────────────────────

export const ROUTES = {
  home: '/',
  about: '/about',
  cart: '/cart',
  checkout: '/checkout',
  collections: '/collections',
  products: '/products',
  search: '/search',
  wishlist: '/wishlist',
  contact: '/contact',
  faq: '/faq',
  privacy: '/privacy',
  terms: '/terms',
  shippingReturns: '/shipping-returns',
  storeLocator: '/store-locator',
  login: '/account/login',
  register: '/account/register',
  forgotPassword: '/account/forgot-password',
  resetPassword: '/account/reset-password',
  account: '/account',
} as const;
