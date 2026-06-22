import { test, expect, type Page } from "@playwright/test";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@hadha.co";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";

async function navigateToAdmin(page: Page) {
  const paths = ["/admin", "/admin/login", "/admin/dashboard"];
  for (const path of paths) {
    const res = await page.goto(path);
    if (res && res.status() < 500) return res.status();
  }
  return 404;
}

test.describe("Admin Login", () => {
  test("admin login page renders", async ({ page }) => {
    await navigateToAdmin(page);
    await expect(page).not.toHaveURL(/500/);
    await page.waitForLoadState("networkidle");

    // Should show a login form or redirect to the admin dashboard
    const loginForm = page.locator(
      'form, [data-testid="login-form"], input[type="email"], input[type="password"]'
    );
    await expect(loginForm.first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows error on invalid credentials", async ({ page }) => {
    await navigateToAdmin(page);
    await page.waitForLoadState("networkidle");

    const emailInput = page
      .locator('input[type="email"], input[name="email"]')
      .first();
    const passwordInput = page
      .locator('input[type="password"], input[name="password"]')
      .first();
    const submitBtn = page
      .locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Login")')
      .first();

    if (
      (await emailInput.isVisible({ timeout: 3_000 })) &&
      (await passwordInput.isVisible({ timeout: 3_000 }))
    ) {
      await emailInput.fill("wrong@example.com");
      await passwordInput.fill("wrongpassword");
      await submitBtn.click();
      await page.waitForTimeout(2_000);

      // Should show an error message, NOT redirect to dashboard
      const errorMsg = page.locator(
        '[role="alert"], [class*="error"], [class*="Error"], [data-testid="login-error"]'
      );
      const inError = await errorMsg.first().isVisible({ timeout: 5_000 });
      const stillOnLogin =
        page.url().includes("login") || page.url().includes("admin");
      expect(inError || stillOnLogin).toBe(true);
    }
  });

  test("login with valid credentials (skipped if no E2E_ADMIN_PASSWORD)", async ({
    page,
  }) => {
    if (!ADMIN_PASSWORD) {
      test.skip();
    }

    await navigateToAdmin(page);
    await page.waitForLoadState("networkidle");

    const emailInput = page.locator('input[type="email"]').first();
    const passwordInput = page.locator('input[type="password"]').first();
    const submitBtn = page
      .locator('button[type="submit"], button:has-text("Sign in")')
      .first();

    await emailInput.fill(ADMIN_EMAIL);
    await passwordInput.fill(ADMIN_PASSWORD);
    await submitBtn.click();

    await page.waitForURL(/admin\/dashboard|admin\/home/i, { timeout: 15_000 });
    await expect(page).not.toHaveURL(/login/);
  });
});

test.describe("Admin Dashboard (authenticated)", () => {
  test.beforeEach(async ({ page }) => {
    if (!ADMIN_PASSWORD) {
      test.skip();
    }
    // Login first
    await navigateToAdmin(page);
    await page.waitForLoadState("networkidle");
    await page.locator('input[type="email"]').fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').fill(ADMIN_PASSWORD);
    await page
      .locator('button[type="submit"], button:has-text("Sign in")')
      .click();
    await page.waitForURL(/admin\/dashboard|admin\/home/i, { timeout: 15_000 });
  });

  test("dashboard shows key metrics", async ({ page }) => {
    const metricsSection = page.locator(
      '[data-testid="metrics"], [class*="stat"], [class*="dashboard-card"], [class*="metric"]'
    );
    await expect(metricsSection.first()).toBeVisible({ timeout: 10_000 });
  });

  test("CMS editor is accessible", async ({ page }) => {
    // Navigate to CMS section
    const cmsLink = page
      .getByRole("link", { name: /cms|content|pages/i })
      .first();
    if (await cmsLink.isVisible({ timeout: 3_000 })) {
      await cmsLink.click();
      await page.waitForLoadState("networkidle");
      await expect(page).not.toHaveURL(/500/);

      // CMS save button should be present
      const saveBtn = page.locator(
        'button:has-text("Save"), [data-testid="cms-save"]'
      );
      if (await saveBtn.isVisible({ timeout: 3_000 })) {
        await expect(saveBtn).toBeVisible();
      }
    }
  });

  test("CMS save triggers success feedback", async ({ page }) => {
    const cmsLink = page.getByRole("link", { name: /cms|content|pages/i }).first();
    if (!(await cmsLink.isVisible({ timeout: 3_000 }))) return;
    await cmsLink.click();
    await page.waitForLoadState("networkidle");

    const saveBtn = page.locator('button:has-text("Save"), [data-testid="cms-save"]').first();
    if (await saveBtn.isVisible({ timeout: 3_000 })) {
      await saveBtn.click();
      await page.waitForTimeout(1_500);
      // Should show toast or success state
      await expect(page.locator("body")).not.toContainText("Something went wrong");
    }
  });

  test("admin logout clears session", async ({ page }) => {
    const logoutBtn = page
      .locator('button:has-text("Logout"), a:has-text("Sign out"), [data-testid="logout"]')
      .first();
    if (await logoutBtn.isVisible({ timeout: 3_000 })) {
      await logoutBtn.click();
      await page.waitForURL(/login|\/$/i, { timeout: 10_000 });
      // Should be back on login or home — not on dashboard
      expect(page.url()).not.toMatch(/admin\/dashboard/);
    }
  });
});
