import { test, expect } from '@playwright/test';

test('diagnose: login page DOM', async ({ page }) => {
  await page.goto('/account/login', { waitUntil: 'load' });
  await page.waitForTimeout(3000);
  
  // Log all inputs
  const inputs = page.locator('input');
  const inputCount = await inputs.count();
  console.log(`\n=== LOGIN PAGE: ${inputCount} inputs ===`);
  for (let i = 0; i < inputCount; i++) {
    const input = inputs.nth(i);
    const type = await input.getAttribute('type');
    const name = await input.getAttribute('name');
    const placeholder = await input.getAttribute('placeholder');
    const id = await input.getAttribute('id');
    const ariaLabel = await input.getAttribute('aria-label');
    console.log(`  Input ${i}: type=${type}, name=${name}, placeholder=${placeholder}, id=${id}, aria-label=${ariaLabel}`);
  }
  
  // Log all buttons
  const buttons = page.locator('button');
  const buttonCount = await buttons.count();
  console.log(`\n=== ${buttonCount} buttons ===`);
  for (let i = 0; i < buttonCount; i++) {
    const btn = buttons.nth(i);
    const text = await btn.textContent();
    const ariaLabel = await btn.getAttribute('aria-label');
    console.log(`  Button ${i}: text="${text?.trim()}", aria-label="${ariaLabel}"`);
  }
  
  // Log all links
  const links = page.locator('a');
  const linkCount = await links.count();
  console.log(`\n=== ${linkCount} links ===`);
  for (let i = 0; i < Math.min(linkCount, 15); i++) {
    const link = links.nth(i);
    const text = await link.textContent();
    const href = await link.getAttribute('href');
    console.log(`  Link ${i}: text="${text?.trim()}", href="${href}"`);
  }
  
  // Log headings
  const headings = page.locator('h1, h2, h3');
  const headingCount = await headings.count();
  console.log(`\n=== ${headingCount} headings ===`);
  for (let i = 0; i < headingCount; i++) {
    const h = headings.nth(i);
    const tag = await h.evaluate(el => el.tagName);
    const text = await h.textContent();
    console.log(`  ${tag}: "${text?.trim()}"`);
  }
  
  // Check for promotional popup
  const dialogs = page.locator('[role="dialog"]');
  const dialogCount = await dialogs.count();
  console.log(`\n=== ${dialogCount} dialogs ===`);
  for (let i = 0; i < dialogCount; i++) {
    const d = dialogs.nth(i);
    const classes = await d.getAttribute('class');
    const visible = await d.isVisible();
    console.log(`  Dialog ${i}: visible=${visible}, class="${classes?.substring(0, 100)}"`);
  }
  
  // Screenshot
  await page.screenshot({ path: 'test-results/diag-login.png', fullPage: true });
  
  expect(true).toBe(true);
});

test('diagnose: products page DOM', async ({ page }) => {
  await page.goto('/products', { waitUntil: 'load' });
  await page.waitForTimeout(5000);
  
  const productLinks = page.locator('a[href*="/products/"]');
  const count = await productLinks.count();
  console.log(`\n=== PRODUCTS PAGE: ${count} product links ===`);
  
  // Check for collection links
  const collectionLinks = page.locator('a[href*="/collections/"]');
  const colCount = await collectionLinks.count();
  console.log(`=== ${colCount} collection links ===`);
  
  // Check main content
  const main = page.locator('main');
  const mainText = await main.textContent();
  console.log(`=== Main text (first 500 chars): ${mainText?.substring(0, 500)}`);
  
  // Check for grid/list
  const grid = page.locator('[class*="grid"]');
  const gridCount = await grid.count();
  console.log(`=== ${gridCount} grid elements ===`);
  
  // Log all links
  const links = page.locator('main a');
  const linkCount = await links.count();
  console.log(`\n=== ${linkCount} links in main ===`);
  for (let i = 0; i < Math.min(linkCount, 20); i++) {
    const link = links.nth(i);
    const text = await link.textContent();
    const href = await link.getAttribute('href');
    console.log(`  Link ${i}: text="${text?.trim()?.substring(0, 50)}", href="${href}"`);
  }
  
  await page.screenshot({ path: 'test-results/diag-products.png', fullPage: true });
  
  expect(true).toBe(true);
});

test('diagnose: collections page DOM', async ({ page }) => {
  await page.goto('/collections', { waitUntil: 'load' });
  await page.waitForTimeout(5000);
  
  const collectionLinks = page.locator('a[href*="/collections/"]');
  const count = await collectionLinks.count();
  console.log(`\n=== COLLECTIONS PAGE: ${count} collection links ===`);
  
  const main = page.locator('main');
  const mainText = await main.textContent();
  console.log(`=== Main text (first 500 chars): ${mainText?.substring(0, 500)}`);
  
  // Log all links
  const links = page.locator('main a');
  const linkCount = await links.count();
  console.log(`\n=== ${linkCount} links in main ===`);
  for (let i = 0; i < Math.min(linkCount, 20); i++) {
    const link = links.nth(i);
    const text = await link.textContent();
    const href = await link.getAttribute('href');
    console.log(`  Link ${i}: text="${text?.trim()?.substring(0, 50)}", href="${href}"`);
  }
  
  await page.screenshot({ path: 'test-results/diag-collections.png', fullPage: true });
  
  expect(true).toBe(true);
});

test('diagnose: homepage popup', async ({ page }) => {
  await page.goto('/', { waitUntil: 'load' });
  await page.waitForTimeout(5000);
  
  // Check all dialogs
  const dialogs = page.locator('[role="dialog"]');
  const count = await dialogs.count();
  console.log(`\n=== HOMEPAGE: ${count} dialogs ===`);
  for (let i = 0; i < count; i++) {
    const d = dialogs.nth(i);
    const classes = await d.getAttribute('class');
    const visible = await d.isVisible();
    const ariaModal = await d.getAttribute('aria-modal');
    const html = await d.innerHTML();
    console.log(`  Dialog ${i}: visible=${visible}, aria-modal=${ariaModal}`);
    console.log(`    class="${classes}"`);
    console.log(`    innerHTML (first 300): ${html.substring(0, 300)}`);
  }
  
  await page.screenshot({ path: 'test-results/diag-homepage.png', fullPage: true });
  
  expect(true).toBe(true);
});

test('diagnose: account page after login', async ({ page }) => {
  // Try to login
  await page.goto('/account/login', { waitUntil: 'load' });
  await page.waitForTimeout(3000);
  
  // Try different selectors for email
  const emailSelectors = [
    'input[type="email"]',
    'input[name="email"]',
    'input[placeholder*="email" i]',
    'input[aria-label*="email" i]',
  ];
  
  for (const sel of emailSelectors) {
    const el = page.locator(sel);
    const count = await el.count();
    console.log(`Email selector "${sel}": ${count} matches`);
  }
  
  // Try different selectors for password
  const pwSelectors = [
    'input[type="password"]',
    'input[name="password"]',
    'input[placeholder*="password" i]',
    'input[aria-label*="password" i]',
  ];
  
  for (const sel of pwSelectors) {
    const el = page.locator(sel);
    const count = await el.count();
    console.log(`Password selector "${sel}": ${count} matches`);
  }
  
  // Try filling and submitting
  const emailInput = page.locator('input[type="email"]').first();
  const pwInput = page.locator('input[type="password"]').first();
  
  if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await emailInput.fill('testcustomer@hadha.co');
    await pwInput.fill('TestPassword123!');
    
    // Find submit button
    const submitBtns = page.locator('button[type="submit"], button:has-text("Sign In"), button:has-text("sign in"), button:has-text("Log In")');
    const submitCount = await submitBtns.count();
    console.log(`Submit buttons: ${submitCount}`);
    
    if (submitCount > 0) {
      await submitBtns.first().click();
      await page.waitForTimeout(5000);
      console.log(`After login URL: ${page.url()}`);
      
      // Take screenshot
      await page.screenshot({ path: 'test-results/diag-after-login.png', fullPage: true });
      
      // Check what's on the page
      const headings = page.locator('h1, h2, h3');
      const headingCount = await headings.count();
      for (let i = 0; i < headingCount; i++) {
        const text = await headings.nth(i).textContent();
        console.log(`  Heading: "${text?.trim()}"`);
      }
      
      // Check sidebar
      const sidebarBtns = page.locator('button, a').filter({ hasText: /overview|orders|addresses|wishlist|profile|security/i });
      const sidebarCount = await sidebarBtns.count();
      console.log(`Sidebar tabs found: ${sidebarCount}`);
      for (let i = 0; i < sidebarCount; i++) {
        const text = await sidebarBtns.nth(i).textContent();
        console.log(`  Tab: "${text?.trim()}"`);
      }
    }
  } else {
    console.log('No visible email input found');
  }
  
  expect(true).toBe(true);
});

test('diagnose: contact page form', async ({ page }) => {
  await page.goto('/contact', { waitUntil: 'load' });
  await page.waitForTimeout(3000);
  
  const inputs = page.locator('input, textarea, select');
  const count = await inputs.count();
  console.log(`\n=== CONTACT PAGE: ${count} form elements ===`);
  for (let i = 0; i < count; i++) {
    const el = inputs.nth(i);
    const tag = await el.evaluate(el => el.tagName);
    const type = await el.getAttribute('type');
    const name = await el.getAttribute('name');
    const placeholder = await el.getAttribute('placeholder');
    const id = await el.getAttribute('id');
    const ariaLabel = await el.getAttribute('aria-label');
    console.log(`  ${tag}: type=${type}, name=${name}, placeholder=${placeholder}, id=${id}, aria-label=${ariaLabel}`);
  }
  
  await page.screenshot({ path: 'test-results/diag-contact.png', fullPage: true });
  
  expect(true).toBe(true);
});
