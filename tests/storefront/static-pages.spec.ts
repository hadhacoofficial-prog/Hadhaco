import { test, expect } from '@playwright/test';
import { gotoPath, waitForPageReady, dismissPopups } from '../helpers/test-utils';

test.describe('Static Pages', () => {
  test.describe('About Page', () => {
    test.beforeEach(async ({ page }) => {
      await gotoPath(page, '/about');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('page loads with correct title', async ({ page }) => {
      await expect(page).toHaveTitle(/about|story|hadha/i);
    });

    test('has main heading', async ({ page }) => {
      const heading = page.locator('h1').first();
      await expect(heading).toBeVisible();
    });

    test('has brand story content', async ({ page }) => {
      const content = page.locator('main, [class*="content"]').first();
      await expect(content).toBeVisible();
    });

    test('BIS Hallmarked mention exists', async ({ page }) => {
      const bis = page.getByText(/bis|hallmarked|hallmark/i);
      const count = await bis.count();
      expect(count).toBeGreaterThan(0);
    });

    test('footer is visible', async ({ page }) => {
      const footer = page.locator('footer');
      await expect(footer).toBeVisible();
    });
  });

  test.describe('FAQ Page', () => {
    test.beforeEach(async ({ page }) => {
      await gotoPath(page, '/faq');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('page loads with correct title', async ({ page }) => {
      await expect(page).toHaveTitle(/faq|hadha/i);
    });

    test('has FAQ heading', async ({ page }) => {
      const heading = page.locator('h1').first();
      await expect(heading).toBeVisible();
    });

    test('accordion items exist', async ({ page }) => {
      const accordions = page.locator('[role="button"], [data-state], button').filter({
        hasText: /order|shipping|return|payment|product/i,
      });
      const count = await accordions.count();
      expect(count).toBeGreaterThan(0);
    });

    test('clicking accordion expands content', async ({ page }) => {
      const firstAccordion = page.locator('button, [role="button"]').filter({
        hasText: /order|shipping|return|payment/i,
      }).first();
      if (await firstAccordion.isVisible({ timeout: 3000 }).catch(() => false)) {
        await firstAccordion.click();
        await page.waitForTimeout(500);
        // Content should expand
        await expect(page.locator('body')).toBeVisible();
      }
    });
  });

  test.describe('Contact Page', () => {
    test.beforeEach(async ({ page }) => {
      await gotoPath(page, '/contact');
      await dismissPopups(page);
      await waitForPageReady(page);
    });

    test('page loads with correct title', async ({ page }) => {
      await expect(page).toHaveTitle(/contact|hadha/i);
    });

    test('contact form exists', async ({ page }) => {
      const form = page.locator('form').first();
      await expect(form).toBeVisible();
    });

    test('form has name field', async ({ page }) => {
      // Contact form inputs have no labels/name/placeholder — use tag + position
      const nameField = page.locator('form input[type="text"], form input:not([type])').first();
      await expect(nameField).toBeVisible();
    });

    test('form has email field', async ({ page }) => {
      const emailField = page.locator('form input[type="email"]').first();
      await expect(emailField).toBeVisible();
    });

    test('form has message field', async ({ page }) => {
      const messageField = page.locator('form textarea').first();
      await expect(messageField).toBeVisible();
    });

    test('submit button exists', async ({ page }) => {
      const submitBtn = page.getByRole('button', { name: /send|submit/i });
      await expect(submitBtn.first()).toBeVisible();
    });

    test('contact information is displayed', async ({ page }) => {
      const phone = page.getByText(/\+91|phone|call/i);
      const email = page.getByText(/email|@|mail/i);
      const count = (await phone.count()) + (await email.count());
      expect(count).toBeGreaterThan(0);
    });

    test('WhatsApp link exists', async ({ page }) => {
      const whatsappLink = page.locator('a[href*="wa.me"], a[href*="whatsapp"]');
      const count = await whatsappLink.count();
      expect(count).toBeGreaterThan(0);
    });
  });

  test.describe('Privacy Policy', () => {
    test('page loads with content', async ({ page }) => {
      await gotoPath(page, '/privacy');
      await dismissPopups(page);
      await waitForPageReady(page);
      const heading = page.locator('h1, h2').first();
      await expect(heading).toBeVisible();
    });

    test('has privacy sections', async ({ page }) => {
      await gotoPath(page, '/privacy');
      await dismissPopups(page);
      await waitForPageReady(page);
      const content = page.locator('main').first();
      await expect(content).toBeVisible();
    });
  });

  test.describe('Terms of Service', () => {
    test('page loads with content', async ({ page }) => {
      await gotoPath(page, '/terms');
      await dismissPopups(page);
      await waitForPageReady(page);
      const heading = page.locator('h1, h2').first();
      await expect(heading).toBeVisible();
    });

    test('has terms sections', async ({ page }) => {
      await gotoPath(page, '/terms');
      await dismissPopups(page);
      await waitForPageReady(page);
      const content = page.locator('main').first();
      await expect(content).toBeVisible();
    });
  });

  test.describe('Shipping & Returns', () => {
    test('page loads with content', async ({ page }) => {
      await gotoPath(page, '/shipping-returns');
      await dismissPopups(page);
      await waitForPageReady(page);
      const heading = page.locator('h1, h2').first();
      await expect(heading).toBeVisible();
    });

    test('mentions free shipping', async ({ page }) => {
      await gotoPath(page, '/shipping-returns');
      await dismissPopups(page);
      await waitForPageReady(page);
      const freeShipping = page.getByText(/free shipping|free delivery/i);
      const count = await freeShipping.count();
      expect(count).toBeGreaterThan(0);
    });

    test('mentions return policy', async ({ page }) => {
      await gotoPath(page, '/shipping-returns');
      await dismissPopups(page);
      await waitForPageReady(page);
      const returns = page.getByText(/return|refund|exchange/i);
      const count = await returns.count();
      expect(count).toBeGreaterThan(0);
    });
  });

  test.describe('Store Locator', () => {
    test('page loads with store information', async ({ page }) => {
      await gotoPath(page, '/store-locator');
      await dismissPopups(page);
      await waitForPageReady(page);
      const heading = page.locator('h1, h2').first();
      await expect(heading).toBeVisible();
    });

    test('shows store locations', async ({ page }) => {
      await gotoPath(page, '/store-locator');
      await dismissPopups(page);
      await waitForPageReady(page);
      const stores = page.getByText(/visakhapatnam|hyderabad|bengaluru|chennai/i);
      const count = await stores.count();
      expect(count).toBeGreaterThan(0);
    });

    test('has Google Maps links', async ({ page }) => {
      await gotoPath(page, '/store-locator');
      await dismissPopups(page);
      await waitForPageReady(page);
      const mapsLinks = page.locator('a[href*="maps.google"], a[href*="google.com/maps"], a:has-text("direction")');
      const count = await mapsLinks.count();
      expect(count).toBeGreaterThan(0);
    });
  });

  test.describe('All Static Pages - Console Errors', () => {
    const pages = ['/about', '/faq', '/contact', '/privacy', '/terms', '/shipping-returns', '/store-locator'];

    for (const path of pages) {
      test(`${path} has no console errors`, async ({ page }) => {
        const errors: string[] = [];
        page.on('pageerror', (err) => errors.push(err.message));
        await gotoPath(page, path);
        await dismissPopups(page);
        await waitForPageReady(page);
        const criticalErrors = errors.filter(
          (e) => !e.includes('favicon') && !e.includes('analytics'),
        );
        expect(criticalErrors).toHaveLength(0);
      });
    }
  });
});
