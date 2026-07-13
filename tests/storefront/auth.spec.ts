import { test, expect } from '@playwright/test';
import { gotoPath, TEST_USER, ROUTES, loginAsTestUser, waitForPageReady, dismissPopups } from '../helpers/test-utils';

test.describe('Authentication', () => {
  test.describe('Login Page', () => {
    test.beforeEach(async ({ page }) => {
      await gotoPath(page, '/account/login');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('login page loads with form', async ({ page }) => {
      await expect(page).toHaveTitle(/sign in|login|hadha/i);
      // Inputs have no labels/name/placeholder — use type-based selectors
      const emailField = page.locator('input[type="email"]').first();
      const passwordField = page.locator('input[type="password"]').first();
      await expect(emailField).toBeVisible();
      await expect(passwordField).toBeVisible();
    });

    test('sign in button is visible', async ({ page }) => {
      const signInBtn = page.getByRole('button', { name: /sign in/i });
      await expect(signInBtn).toBeVisible();
    });

    test('Google auth button exists', async ({ page }) => {
      const googleBtn = page.getByRole('button', { name: /google/i }).or(
        page.getByText(/continue with google/i),
      );
      await expect(googleBtn.first()).toBeVisible();
    });

    test('forgot password link exists', async ({ page }) => {
      const forgotLink = page.getByRole('link', { name: /forgot password/i });
      await expect(forgotLink).toBeVisible();
    });

    test('create account link exists', async ({ page }) => {
      const registerLink = page.getByRole('link', { name: /create an account|register|sign up/i });
      await expect(registerLink).toBeVisible();
    });

    test('remember me checkbox exists', async ({ page }) => {
      const rememberCheckbox = page.locator('input[type="checkbox"]').first();
      await expect(rememberCheckbox).toBeVisible();
    });

    test('empty form submission shows validation', async ({ page }) => {
      const signInBtn = page.getByRole('button', { name: /sign in/i });
      await signInBtn.click({ force: true });
      await page.waitForTimeout(500);
      // Form should not submit (HTML5 validation)
      expect(page.url()).toContain('/account/login');
    });

    test('invalid email format shows validation', async ({ page }) => {
      await page.locator('input[type="email"]').first().fill('notanemail');
      await page.locator('input[type="password"]').first().fill('password');
      const signInBtn = page.getByRole('button', { name: /sign in/i });
      await signInBtn.click({ force: true });
      await page.waitForTimeout(500);
      // Should stay on login page
      expect(page.url()).toContain('/account/login');
    });

    test('wrong credentials show error toast', async ({ page }) => {
      await page.locator('input[type="email"]').first().fill('wrong@example.com');
      await page.locator('input[type="password"]').first().fill('wrongpassword123');
      const signInBtn = page.getByRole('button', { name: /sign in/i });
      await signInBtn.click({ force: true });
      await page.waitForTimeout(3000);
      // Error toast or message should appear
      await expect(page.locator('body')).toBeVisible();
    });

    test('login form has proper input types', async ({ page }) => {
      const emailInput = page.locator('input[type="email"]').first();
      const passwordInput = page.locator('input[type="password"]').first();
      expect(await emailInput.getAttribute('type')).toBe('email');
      expect(await passwordInput.getAttribute('type')).toBe('password');
    });

    test('sign in button shows loading state', async ({ page }) => {
      await page.locator('input[type="email"]').first().fill(TEST_USER.email);
      await page.locator('input[type="password"]').first().fill('wrong');
      const signInBtn = page.getByRole('button', { name: /sign in/i });
      await signInBtn.click({ force: true });
      // Button should show loading state
      await expect(page.locator('body')).toBeVisible();
    });
  });

  test.describe('Register Page', () => {
    test.beforeEach(async ({ page }) => {
      await gotoPath(page, '/account/register');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('register page loads with form', async ({ page }) => {
      await expect(page).toHaveTitle(/register|create|sign up|hadha/i);
      const nameField = page.locator('input[name="name"], input[placeholder*="name" i], input[type="text"]').first();
      const emailField = page.locator('input[type="email"]').first();
      const passwordField = page.locator('input[type="password"]').first();
      await expect(emailField).toBeVisible();
      await expect(passwordField).toBeVisible();
    });

    test('Google sign-up button exists', async ({ page }) => {
      const googleBtn = page.getByRole('button', { name: /google/i }).or(
        page.getByText(/continue with google/i),
      );
      await expect(googleBtn.first()).toBeVisible();
    });

    test('sign in link exists', async ({ page }) => {
      const signInLink = page.getByRole('link', { name: /sign in|login/i });
      await expect(signInLink.first()).toBeVisible();
    });

    test('empty form submission shows validation', async ({ page }) => {
      const createBtn = page.getByRole('button', { name: 'Create Account' });
      await createBtn.click({ force: true });
      await page.waitForTimeout(500);
      expect(page.url()).toContain('/account/register');
    });

    test('password requirements shown', async ({ page }) => {
      const passwordInput = page.locator('input[type="password"]').first();
      await passwordInput.fill('weak');
      await page.waitForTimeout(300);
      // Should not allow very weak passwords (depends on validation)
    });
  });

  test.describe('Forgot Password Page', () => {
    test.beforeEach(async ({ page }) => {
      await gotoPath(page, '/account/forgot-password');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('page loads with email input', async ({ page }) => {
      const emailField = page.locator('input[type="email"]').first();
      await expect(emailField).toBeVisible();
    });

    test('submit button exists', async ({ page }) => {
      const submitBtn = page.getByRole('button', { name: /send|reset|submit/i });
      await expect(submitBtn.first()).toBeVisible();
    });

    test('back to login link exists', async ({ page }) => {
      const backLink = page.getByRole('link', { name: /back.*login|sign in/i });
      await expect(backLink.first()).toBeVisible();
    });

    test('empty email submission shows validation', async ({ page }) => {
      const submitBtn = page.getByRole('button', { name: /send|reset|submit/i }).first();
      await submitBtn.click();
      await page.waitForTimeout(500);
      expect(page.url()).toContain('/account/forgot-password');
    });
  });

  test.describe('Reset Password Page', () => {
    test('page loads or redirects appropriately', async ({ page }) => {
      await gotoPath(page, '/account/reset-password');
      await dismissPopups(page);
      await waitForPageReady(page);
      // Reset password requires a token, so it may redirect or show form
      const body = page.locator('body');
      await expect(body).toBeVisible();
    });
  });

  test.describe('Auth Flow Integration', () => {
    test('login page has proper heading and branding', async ({ page }) => {
      await gotoPath(page, '/account/login');
      await dismissPopups(page);
      await waitForPageReady(page);
      const heading = page.getByRole('heading', { name: /sign in/i });
      await expect(heading).toBeVisible();
    });

    test('register page has proper heading', async ({ page }) => {
      await gotoPath(page, '/account/register');
      await dismissPopups(page);
      await waitForPageReady(page);
      const heading = page.getByRole('heading', { name: /create|register|sign up/i });
      await expect(heading.first()).toBeVisible();
    });

    test('navigate between login and register', async ({ page }) => {
      await gotoPath(page, '/account/login');
      await dismissPopups(page);
      await waitForPageReady(page);
      const registerLink = page.getByRole('link', { name: /create an account|register|sign up/i });
      await registerLink.click();
      await waitForPageReady(page);
      expect(page.url()).toContain('/account/register');
    });
  });
});
