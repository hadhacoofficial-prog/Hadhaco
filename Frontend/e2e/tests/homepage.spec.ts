import { test, expect } from "@playwright/test";

test.describe("Homepage", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders without error", async ({ page }) => {
    await expect(page).not.toHaveTitle(/error|not found/i);
    expect(page.url()).toContain("/");
  });

  test("displays hero section", async ({ page }) => {
    // Hero / banner section should be visible above the fold
    const hero = page
      .locator('[data-testid="hero"], section:first-of-type, [class*="hero"], [class*="banner"]')
      .first();
    await expect(hero).toBeVisible({ timeout: 10_000 });
  });

  test("shows navigation links", async ({ page }) => {
    const nav = page.locator("nav, header").first();
    await expect(nav).toBeVisible();
  });

  test("displays featured products or collections", async ({ page }) => {
    // Look for a product card or collection section
    const products = page.locator(
      '[data-testid="product-card"], [class*="product"], [class*="collection"]'
    );
    await expect(products.first()).toBeVisible({ timeout: 15_000 });
  });

  test("has working navigation to shop", async ({ page }) => {
    const shopLink = page.getByRole("link", { name: /shop|products|jewellery|catalogue/i }).first();
    if (await shopLink.isVisible()) {
      await shopLink.click();
      await page.waitForURL(/shop|products|category|catalogue/i);
      await expect(page).not.toHaveURL("/404");
    }
  });

  test("page loads within performance budget", async ({ page }) => {
    const startTime = Date.now();
    await page.goto("/", { waitUntil: "networkidle" });
    const loadTime = Date.now() - startTime;
    // 10s budget — accounts for cold starts in CI
    expect(loadTime).toBeLessThan(10_000);
  });

  test("has no broken images in viewport", async ({ page }) => {
    const brokenImages = await page.evaluate(() =>
      Array.from(document.images)
        .filter((img) => img.complete && img.naturalWidth === 0 && img.src)
        .map((img) => img.src)
    );
    expect(brokenImages).toHaveLength(0);
  });
});
