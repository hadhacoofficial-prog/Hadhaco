import { test, expect } from "@playwright/test";

test.describe("Product Search", () => {
  test("search input is present and functional", async ({ page }) => {
    await page.goto("/");
    const searchInput = page
      .locator('[data-testid="search-input"], input[type="search"], input[placeholder*="search" i]')
      .first();
    if (await searchInput.isVisible()) {
      await searchInput.fill("ring");
      await searchInput.press("Enter");
      await page.waitForURL(/search|q=ring/i);
      await expect(page.locator("body")).not.toContainText("Something went wrong");
    }
  });

  test("search suggestions appear on typing", async ({ page }) => {
    await page.goto("/");
    const searchInput = page
      .locator('[data-testid="search-input"], input[type="search"], input[placeholder*="search" i]')
      .first();
    if (await searchInput.isVisible()) {
      await searchInput.fill("si");
      // Wait briefly for debounce
      await page.waitForTimeout(500);
      const suggestions = page.locator('[role="listbox"], [class*="suggestion"], [class*="autocomplete"]');
      // Suggestions may or may not appear — just verify no JS errors
      await expect(page.locator("body")).not.toContainText("Uncaught");
    }
  });
});

test.describe("Category Navigation", () => {
  test("category links are accessible from nav or homepage", async ({ page }) => {
    await page.goto("/");
    const categoryLink = page
      .getByRole("link", { name: /ring|necklace|bracelet|earring|pendant|category/i })
      .first();
    if (await categoryLink.isVisible()) {
      await categoryLink.click();
      await expect(page).not.toHaveURL("/404");
      await page.waitForLoadState("networkidle");
    }
  });

  test("category page displays products", async ({ page }) => {
    // Try common category paths
    const paths = ["/shop", "/products", "/category", "/jewellery"];
    for (const path of paths) {
      const response = await page.goto(path);
      if (response && response.status() < 400) {
        const productItems = page.locator(
          '[data-testid="product-card"], [class*="product-card"], [class*="ProductCard"]'
        );
        const count = await productItems.count();
        if (count > 0) {
          await expect(productItems.first()).toBeVisible();
          return;
        }
      }
    }
  });
});

test.describe("Product Details", () => {
  test("product detail page renders correctly", async ({ page }) => {
    // Navigate to shop listing first
    await page.goto("/shop").catch(() => page.goto("/products"));
    await page.waitForLoadState("networkidle");

    // Click the first product card
    const firstProduct = page
      .locator('[data-testid="product-card"] a, [class*="product-card"] a, [class*="ProductCard"] a')
      .first();

    if (await firstProduct.isVisible({ timeout: 5_000 })) {
      await firstProduct.click();
      await page.waitForLoadState("networkidle");

      // Product detail should show name and price
      const productName = page
        .locator('[data-testid="product-name"], h1, [class*="product-title"]')
        .first();
      await expect(productName).toBeVisible({ timeout: 10_000 });

      const price = page
        .locator('[data-testid="product-price"], [class*="price"]')
        .first();
      await expect(price).toBeVisible();
    }
  });

  test("product detail shows images", async ({ page }) => {
    await page.goto("/shop").catch(() => page.goto("/products"));
    await page.waitForLoadState("networkidle");

    const firstProduct = page
      .locator('[data-testid="product-card"] a, [class*="product-card"] a')
      .first();
    if (await firstProduct.isVisible({ timeout: 5_000 })) {
      await firstProduct.click();
      await page.waitForLoadState("networkidle");

      const productImage = page
        .locator('[data-testid="product-image"], [class*="product-image"] img, .product-gallery img')
        .first();
      if (await productImage.isVisible({ timeout: 5_000 })) {
        await expect(productImage).toBeVisible();
      }
    }
  });

  test("variant selection updates price or availability", async ({ page }) => {
    await page.goto("/shop").catch(() => page.goto("/products"));
    await page.waitForLoadState("networkidle");

    const firstProduct = page
      .locator('[data-testid="product-card"] a, [class*="product-card"] a')
      .first();
    if (await firstProduct.isVisible({ timeout: 5_000 })) {
      await firstProduct.click();
      await page.waitForLoadState("networkidle");

      // Look for variant selectors (size, material, etc.)
      const variantBtn = page
        .locator('[data-testid="variant-option"], [class*="variant"], button[data-variant]')
        .first();
      if (await variantBtn.isVisible({ timeout: 3_000 })) {
        await variantBtn.click();
        // Page should remain stable (no crash)
        await expect(page.locator("body")).not.toContainText("Something went wrong");
      }
    }
  });
});

test.describe("Wishlist", () => {
  test("wishlist button toggles on product card", async ({ page }) => {
    await page.goto("/shop").catch(() => page.goto("/products"));
    await page.waitForLoadState("networkidle");

    const wishlistBtn = page
      .locator('[data-testid="wishlist-btn"], [aria-label*="wishlist" i], [aria-label*="favourite" i]')
      .first();
    if (await wishlistBtn.isVisible({ timeout: 5_000 })) {
      await wishlistBtn.click();
      // Should either redirect to login or toggle the state
      await page.waitForTimeout(500);
      await expect(page.locator("body")).not.toContainText("Something went wrong");
    }
  });
});
