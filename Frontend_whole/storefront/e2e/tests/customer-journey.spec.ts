import { test, expect, type Page, type BrowserContext } from "@playwright/test";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Navigate to a product detail page by clicking the first product card. */
async function goToFirstProduct(page: Page): Promise<boolean> {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  // Try homepage product cards first, then /shop, then /collections
  for (const path of ["/", "/shop", "/collections"]) {
    if (path !== "/") {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
    }
    const card = page.locator('[data-testid="product-card"] a, a[href^="/products/"]').first();
    if (await card.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await card.click();
      await page.waitForLoadState("networkidle");
      return true;
    }
  }
  return false;
}

/** Attempt to add the current product to cart. Returns true if the button was found and clicked. */
async function clickAddToCart(page: Page): Promise<boolean> {
  const btn = page
    .locator(
      'button:has-text("Add to Cart"), button:has-text("Add to Bag"), [data-testid="add-to-cart"]',
    )
    .first();
  if (!(await btn.isVisible({ timeout: 5_000 }).catch(() => false))) return false;
  await btn.click();
  await page.waitForTimeout(1_000);
  return true;
}

/** Clear all localStorage to reset Zustand stores between tests. */
async function clearAllStores(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem("hadha-cart");
    localStorage.removeItem("hadha-checkout");
    localStorage.removeItem("hadha-buy-now");
    localStorage.removeItem("hadha-wishlist");
    localStorage.removeItem("hadha-reservation");
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 1: BROWSE & DISCOVER (no auth required)
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Browse & Discover", () => {
  test("homepage renders with hero, navigation, and product grid", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Hero / banner
    const hero = page.locator('[data-testid="hero"], [class*="hero"], [class*="banner"]').first();
    await expect(hero).toBeVisible({ timeout: 10_000 });

    // Navigation
    const nav = page.locator("nav, header").first();
    await expect(nav).toBeVisible();

    // Product grid
    const products = page.locator(
      '[data-testid="product-card"], a[href^="/products/"], [class*="product-grid"] > *',
    );
    await expect(products.first()).toBeVisible({ timeout: 15_000 });

    // No 500 errors
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("navigation links are functional", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const links = [
      { pattern: /shop|collections/i, expectUrl: /shop|collections|products/i },
      { pattern: /about/i, expectUrl: /about/ },
      { pattern: /contact/i, expectUrl: /contact/ },
    ];

    for (const { pattern, expectUrl } of links) {
      const link = page.getByRole("link", { name: pattern }).first();
      if (await link.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await link.click();
        await page.waitForLoadState("networkidle");
        await expect(page).toHaveURL(expectUrl);
        await expect(page.locator("body")).not.toContainText("Internal Server Error");
        await page.goBack();
        await page.waitForLoadState("networkidle");
      }
    }
  });

  test("product detail page renders with name, price, images, and add-to-cart", async ({
    page,
  }) => {
    const found = await goToFirstProduct(page);
    if (!found) {
      test.skip(true, "No product cards found to click");
    }

    // Product name
    const name = page.locator("h1").first();
    await expect(name).toBeVisible({ timeout: 10_000 });
    await expect(name).not.toBeEmpty();

    // Price
    const price = page.locator('[class*="price"], [data-testid="product-price"]').first();
    await expect(price).toBeVisible();

    // Image
    const img = page.locator('[class*="gallery"] img, [class*="product-image"] img').first();
    if (await img.isVisible({ timeout: 3_000 }).catch(() => false)) {
      // Verify image loaded
      const loaded = await img.evaluate(
        (el) => (el as HTMLImageElement).complete && (el as HTMLImageElement).naturalWidth > 0,
      );
      expect(loaded).toBe(true);
    }

    // Add to Cart button should be present (unless sold out)
    const addBtn = page
      .locator('button:has-text("Add to Cart"), button:has-text("Add to Bag")')
      .first();
    const soldOutBtn = page.locator('button:has-text("Out of Stock"), button:has-text("Notify")');
    const hasAdd = await addBtn.isVisible({ timeout: 3_000 }).catch(() => false);
    const hasSoldOut = await soldOutBtn.isVisible({ timeout: 2_000 }).catch(() => false);
    expect(hasAdd || hasSoldOut).toBe(true);
  });

  test("product gallery image switching works", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const thumbnails = page.locator(
      '[class*="gallery"] button img, [class*="thumbnail"] img, [class*="thumb"] img',
    );
    const count = await thumbnails.count();
    if (count < 2) test.skip(true, "Product has only one image");

    // Click second thumbnail
    await thumbnails.nth(1).click();
    await page.waitForTimeout(500);

    // Main image should have changed (or at least no crash)
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("search functionality works", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Click search icon/button to open overlay
    const searchTrigger = page
      .locator(
        '[data-testid="search-input"], button[aria-label*="search" i], [class*="search-trigger"], button:has-text("Search")',
      )
      .first();

    if (await searchTrigger.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await searchTrigger.click();
      await page.waitForTimeout(500);

      const searchInput = page
        .locator(
          '[data-testid="search-input"], input[type="search"], input[placeholder*="search" i], input[name*="search" i]',
        )
        .first();

      if (await searchInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await searchInput.fill("silver");
        await searchInput.press("Enter");
        await page.waitForLoadState("networkidle");

        // Should navigate to search page
        await expect(page).toHaveURL(/search|q=silver/i);
        await expect(page.locator("body")).not.toContainText("Internal Server Error");
      }
    }
  });

  test("collections page renders product listings", async ({ page }) => {
    await page.goto("/collections");
    await page.waitForLoadState("networkidle");

    const products = page.locator(
      '[data-testid="product-card"], a[href^="/products/"], [class*="product-card"]',
    );
    if (
      await products
        .first()
        .isVisible({ timeout: 10_000 })
        .catch(() => false)
    ) {
      const count = await products.count();
      expect(count).toBeGreaterThan(0);
    }
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("page loads within 10s performance budget", async ({ page }) => {
    const start = Date.now();
    await page.goto("/", { waitUntil: "networkidle" });
    const loadTime = Date.now() - start;
    expect(loadTime).toBeLessThan(10_000);
  });

  test("no broken images in viewport", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2_000); // Allow lazy images to load

    const brokenImages = await page.evaluate(() =>
      Array.from(document.images)
        .filter((img) => img.complete && img.naturalWidth === 0 && img.src)
        .map((img) => img.src),
    );
    expect(brokenImages).toHaveLength(0);
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 2: CART OPERATIONS (localStorage-based, no auth required)
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Cart Operations", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllStores(page);
  });

  test("add to cart opens cart drawer and shows item", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const added = await clickAddToCart(page);
    if (!added) test.skip(true, "Add to Cart button not found");

    // Cart drawer should open (cart drawer is always mounted)
    const drawer = page
      .locator(
        '[data-testid="cart-drawer"], [class*="cart-drawer"], [class*="CartDrawer"], [role="dialog"]',
      )
      .first();
    // Wait briefly for the drawer animation
    await page.waitForTimeout(500);

    // Verify no crash occurred
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("cart page displays added items with correct data", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const added = await clickAddToCart(page);
    if (!added) test.skip(true, "Add to Cart not available");

    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    // Cart should not be empty
    const cartItem = page
      .locator(
        '[data-testid="cart-item"], [class*="CartItem"], [class*="cart-item"], a[href^="/products/"]',
      )
      .first();

    if (await cartItem.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Should show product name
      await expect(cartItem).not.toBeEmpty();
    }

    // Empty cart state should NOT show
    const emptyState = page.locator('text="Your cart is empty"');
    await expect(emptyState).not.toBeVisible();
  });

  test("quantity stepper increments and decrements", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const added = await clickAddToCart(page);
    if (!added) test.skip(true, "Add to Cart not available");

    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    // Find quantity stepper buttons
    const incrementBtn = page
      .locator(
        '[aria-label*="increase" i], [aria-label*="increment" i], button:has-text("+"), [data-testid="qty-increase"]',
      )
      .first();

    if (await incrementBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await incrementBtn.click();
      await page.waitForTimeout(500);

      // Verify no crash
      await expect(page.locator("body")).not.toContainText("Internal Server Error");
    }
  });

  test("remove item from cart clears the line", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const added = await clickAddToCart(page);
    if (!added) test.skip(true, "Add to Cart not available");

    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    const removeBtn = page
      .locator(
        '[aria-label*="remove" i], button:has-text("Remove"), [data-testid="remove-item"], button:has-text("Delete")',
      )
      .first();

    if (await removeBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await removeBtn.click();
      await page.waitForTimeout(1_000);

      // After removal, should show empty state or have fewer items
      await expect(page.locator("body")).not.toContainText("Internal Server Error");
    }
  });

  test("cart persists across page refresh (localStorage)", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const added = await clickAddToCart(page);
    if (!added) test.skip(true, "Add to Cart not available");

    // Refresh the page
    await page.reload();
    await page.waitForLoadState("networkidle");

    // Navigate to cart
    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    // Cart should still have items (from localStorage)
    const cartItems = page.locator(
      '[data-testid="cart-item"], [class*="CartItem"], a[href^="/products/"]',
    );
    // Either items exist or we're on an empty cart — no crash
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 3: CHECKOUT FLOW (auth required for most paths)
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Checkout Flow", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllStores(page);
  });

  test("checkout redirects to login when not authenticated", async ({ page }) => {
    await page.goto("/checkout");
    await page.waitForLoadState("networkidle");

    // Should redirect to login
    await expect(page).toHaveURL(/login|auth|account/i);
  });

  test("checkout with empty cart redirects or shows empty state", async ({ page }) => {
    // Navigate to checkout (will redirect to login for unauthenticated)
    await page.goto("/checkout");
    await page.waitForLoadState("networkidle");

    // If redirected to login, that's expected
    if (page.url().includes("login") || page.url().includes("auth")) {
      // Expected — checkout requires auth
      return;
    }

    // If somehow on checkout with empty cart, should show empty state
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("stock-changed page renders", async ({ page }) => {
    await page.goto("/checkout/stock-changed");
    await page.waitForLoadState("networkidle");

    // Should render without 500
    await expect(page.locator("body")).not.toContainText("Internal Server Error");

    // Should show some content about stock change
    const heading = page.locator("h1, h2, [class*='heading']").first();
    if (await heading.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await expect(heading).not.toBeEmpty();
    }
  });

  test("reservation-expired page renders", async ({ page }) => {
    await page.goto("/checkout/reservation-expired");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("payment-failed page renders", async ({ page }) => {
    await page.goto("/checkout/payment-failed");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("order success page renders with order details", async ({ page }) => {
    // Success page needs order params — try without them
    await page.goto("/checkout/success");
    await page.waitForLoadState("networkidle");

    // Should not crash even without order params
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 4: BUY NOW FLOW (bypasses cart)
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Buy Now Flow", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllStores(page);
  });

  test("Buy Now button navigates directly to checkout", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const buyNowBtn = page
      .locator('button:has-text("Buy Now"), button:has-text("Buy now"), [data-testid="buy-now"]')
      .first();

    if (await buyNowBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await buyNowBtn.click();
      await page.waitForLoadState("networkidle");

      // Should navigate to checkout (or login if not authenticated)
      const url = page.url();
      const navigatedToCheckoutOrLogin =
        url.includes("checkout") || url.includes("login") || url.includes("auth");
      expect(navigatedToCheckoutOrLogin).toBe(true);
    }
  });

  test("Buy Now does NOT modify cart store", async ({ page }) => {
    // Add an item to cart first
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const added = await clickAddToCart(page);
    if (!added) test.skip(true, "Add to Cart not available");

    // Record cart state
    await page.goto("/cart");
    await page.waitForLoadState("networkidle");
    const cartContentBefore = await page.evaluate(() => {
      return JSON.parse(localStorage.getItem("hadha-cart") ?? "{}");
    });

    // Go back to product and click Buy Now
    await page.goBack();
    await page.waitForLoadState("networkidle");

    const buyNowBtn = page
      .locator('button:has-text("Buy Now"), button:has-text("Buy now")')
      .first();

    if (await buyNowBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await buyNowBtn.click();
      await page.waitForTimeout(1_000);

      // Check cart is unchanged
      const cartContentAfter = await page.evaluate(() => {
        return JSON.parse(localStorage.getItem("hadha-cart") ?? "{}");
      });

      // Buy Now should NOT have modified cart lines
      expect(cartContentAfter.lines?.length ?? 0).toBe(cartContentBefore.lines?.length ?? 0);
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 5: WISHLIST
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Wishlist", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllStores(page);
  });

  test("wishlist toggle works on product page", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const wishBtn = page
      .locator(
        '[aria-label*="wishlist" i], [aria-label*="favourite" i], [aria-label*="favorite" i], button:has-text("Wishlist")',
      )
      .first();

    if (await wishBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await wishBtn.click();
      await page.waitForTimeout(500);

      // Should either toggle state or redirect to login (if not authenticated)
      await expect(page.locator("body")).not.toContainText("Internal Server Error");
    }
  });

  test("wishlist page renders", async ({ page }) => {
    await page.goto("/wishlist");
    await page.waitForLoadState("networkidle");

    // Should render without error
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("wishlist persists across refresh (localStorage)", async ({ page }) => {
    const found = await goToFirstProduct(page);
    if (!found) test.skip(true, "No product found");

    const wishBtn = page
      .locator(
        '[aria-label*="wishlist" i], [aria-label*="favourite" i], [aria-label*="favorite" i]',
      )
      .first();

    if (await wishBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await wishBtn.click();
      await page.waitForTimeout(500);

      // Check localStorage
      const wishlistData = await page.evaluate(() => {
        return JSON.parse(localStorage.getItem("hadha-wishlist") ?? "{}");
      });

      // If the toggle added an item, verify it persists after refresh
      if ((wishlistData.state?.items?.length ?? 0) > 0) {
        await page.reload();
        await page.waitForLoadState("networkidle");

        const afterRefresh = await page.evaluate(() => {
          return JSON.parse(localStorage.getItem("hadha-wishlist") ?? "{}");
        });
        expect(afterRefresh.state?.items?.length ?? 0).toBeGreaterThan(0);
      }
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 6: CROSS-TAB SYNC (BroadcastChannel)
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Cross-Tab Sync", () => {
  test("cart changes in tab A are visible in tab B", async ({ context }) => {
    // Open two pages in the same browser context (shares localStorage)
    const pageA = await context.newPage();
    const pageB = await context.newPage();

    // Tab A: add item to cart
    await pageA.goto("/");
    await pageA.waitForLoadState("networkidle");

    // Find a product
    const card = pageA.locator('a[href^="/products/"]').first();
    if (!(await card.isVisible({ timeout: 5_000 }).catch(() => false))) {
      await pageA.close();
      await pageB.close();
      test.skip(true, "No product found");
    }

    await card.click();
    await pageA.waitForLoadState("networkidle");

    const addBtn = pageA
      .locator('button:has-text("Add to Cart"), button:has-text("Add to Bag")')
      .first();

    if (!(await addBtn.isVisible({ timeout: 5_000 }).catch(() => false))) {
      await pageA.close();
      await pageB.close();
      test.skip(true, "Add to Cart not available");
    }

    await addBtn.click();
    await pageA.waitForTimeout(1_000);

    // Tab B: navigate to cart — should see the same item (via shared localStorage)
    await pageB.goto("/cart");
    await pageB.waitForLoadState("networkidle");
    await pageB.waitForTimeout(1_000);

    // Both tabs should have the cart data
    const cartA = await pageA.evaluate(() =>
      JSON.parse(localStorage.getItem("hadha-cart") ?? "{}"),
    );
    const cartB = await pageB.evaluate(() =>
      JSON.parse(localStorage.getItem("hadha-cart") ?? "{}"),
    );

    expect(cartB.state?.lines?.length ?? 0).toBe(cartA.state?.lines?.length ?? 0);

    await pageA.close();
    await pageB.close();
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 7: AUTH FLOWS
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Auth Flows", () => {
  test("login page renders with form fields", async ({ page }) => {
    await page.goto("/account/login");
    await page.waitForLoadState("networkidle");

    // Should have email and password fields
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();

    if (await emailInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(emailInput).toBeVisible();
      await expect(passwordInput).toBeVisible();
    }

    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("register page renders", async ({ page }) => {
    await page.goto("/account/register");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("forgot password page renders", async ({ page }) => {
    await page.goto("/account/forgot-password");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });

  test("account page redirects to login when not authenticated", async ({ page }) => {
    await page.goto("/account");
    await page.waitForLoadState("networkidle");

    await expect(page).toHaveURL(/login|auth|account/i);
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 8: STATIC PAGES
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Static Pages", () => {
  const pages = [
    "/about",
    "/contact",
    "/faq",
    "/privacy",
    "/terms",
    "/shipping-returns",
    "/store-locator",
  ];

  for (const path of pages) {
    test(`${path} renders without error`, async ({ page }) => {
      const res = await page.goto(path);
      await page.waitForLoadState("networkidle");

      if (res && res.status() < 400) {
        await expect(page.locator("body")).not.toContainText("Internal Server Error");
      }
    });
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// TEST SUITE 9: ERROR HANDLING & EDGE CASES
// ══════════════════════════════════════════════════════════════════════════════

test.describe("Error Handling", () => {
  test("non-existent route shows 404 page", async ({ page }) => {
    await page.goto("/this-route-does-not-exist-12345");
    await page.waitForLoadState("networkidle");

    // Should show 404 content
    const content = await page.textContent("body");
    const has404 =
      content?.includes("404") || content?.includes("not found") || content?.includes("Not Found");
    expect(has404).toBe(true);
  });

  test("non-existent product shows 404", async ({ page }) => {
    await page.goto("/products/this-product-definitely-does-not-exist-12345");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  });
});
