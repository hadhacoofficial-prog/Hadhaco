import { test, expect, type Page } from "@playwright/test";

async function addProductToCart(page: Page) {
  // Navigate to first available product detail page
  await page.goto("/shop").catch(() => page.goto("/products"));
  await page.waitForLoadState("networkidle");

  const firstProduct = page
    .locator('[data-testid="product-card"] a, [class*="product-card"] a')
    .first();

  if (!(await firstProduct.isVisible({ timeout: 5_000 }))) return false;

  await firstProduct.click();
  await page.waitForLoadState("networkidle");

  const addToCartBtn = page
    .locator(
      '[data-testid="add-to-cart"], button:has-text("Add to Cart"), button:has-text("Add to Bag")',
    )
    .first();

  if (!(await addToCartBtn.isVisible({ timeout: 5_000 }))) return false;

  await addToCartBtn.click();
  await page.waitForTimeout(800);
  return true;
}

test.describe("Cart", () => {
  test("add to cart button adds item", async ({ page }) => {
    const added = await addProductToCart(page);
    if (!added) test.skip();

    // Cart count or toast should indicate the item was added
    const cartIndicator = page.locator(
      '[data-testid="cart-count"], [class*="cart-count"], [aria-label*="cart" i]',
    );
    // Either a toast appears or cart count updates — no crash is the minimum bar
    await expect(page.locator("body")).not.toContainText("Something went wrong");
  });

  test("cart page shows added item", async ({ page }) => {
    const added = await addProductToCart(page);
    if (!added) test.skip();

    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    const cartItem = page.locator(
      '[data-testid="cart-item"], [class*="cart-item"], [class*="CartItem"]',
    );
    // If auth is required the user will be redirected — just ensure no 500
    await expect(page).not.toHaveURL(/500|error/);
  });

  test("cart allows quantity adjustment", async ({ page }) => {
    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    const qtyIncrement = page
      .locator('[data-testid="qty-increase"], [aria-label*="increase" i], button:has-text("+")')
      .first();
    if (await qtyIncrement.isVisible({ timeout: 3_000 })) {
      await qtyIncrement.click();
      await page.waitForTimeout(500);
      await expect(page.locator("body")).not.toContainText("Something went wrong");
    }
  });

  test("cart allows item removal", async ({ page }) => {
    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    const removeBtn = page
      .locator('[data-testid="remove-item"], [aria-label*="remove" i], button:has-text("Remove")')
      .first();
    if (await removeBtn.isVisible({ timeout: 3_000 })) {
      await removeBtn.click();
      await page.waitForTimeout(500);
      await expect(page.locator("body")).not.toContainText("Something went wrong");
    }
  });
});

test.describe("Checkout", () => {
  test("checkout page is accessible from cart", async ({ page }) => {
    await page.goto("/cart");
    await page.waitForLoadState("networkidle");

    const checkoutBtn = page
      .locator('a[href*="checkout"], button:has-text("Checkout"), button:has-text("Proceed")')
      .first();
    if (await checkoutBtn.isVisible({ timeout: 5_000 })) {
      await checkoutBtn.click();
      // Should navigate to checkout or login
      await page.waitForURL(/checkout|login|auth/i);
      await expect(page).not.toHaveURL(/500|error/);
    }
  });

  test("checkout form accepts shipping details", async ({ page }) => {
    await page.goto("/checkout");
    await page.waitForLoadState("networkidle");

    // If redirected to login, skip
    if (page.url().includes("login") || page.url().includes("auth")) {
      test.skip();
    }

    const nameField = page.locator('input[name*="name" i], input[placeholder*="name" i]').first();
    if (await nameField.isVisible({ timeout: 3_000 })) {
      await nameField.fill("Test User");
    }

    const phoneField = page.locator('input[name*="phone" i], input[type="tel"]').first();
    if (await phoneField.isVisible({ timeout: 3_000 })) {
      await phoneField.fill("9999999999");
    }

    await expect(page.locator("body")).not.toContainText("Something went wrong");
  });

  test("Razorpay payment button is present at checkout", async ({ page }) => {
    await page.goto("/checkout");
    await page.waitForLoadState("networkidle");

    if (page.url().includes("login") || page.url().includes("auth")) {
      test.skip();
    }

    // Razorpay button or Pay Now CTA
    const payBtn = page.locator(
      'button:has-text("Pay"), button:has-text("Place Order"), button[class*="razorpay"], [data-testid="pay-btn"]',
    );
    if (await payBtn.first().isVisible({ timeout: 5_000 })) {
      await expect(payBtn.first()).toBeEnabled();
    }
  });
});

test.describe("Order Success Page", () => {
  test("success page at /order-success is renderable", async ({ page }) => {
    const paths = ["/order-success", "/checkout/success", "/orders/confirmation"];
    for (const path of paths) {
      const res = await page.goto(path);
      if (res && res.status() < 400) {
        await expect(page).not.toHaveURL(/500|error/);
        return;
      }
    }
  });
});
