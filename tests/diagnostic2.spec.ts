import { test } from '@playwright/test';

test('diag: 404 page content', async ({ page }) => {
  await page.goto('/nonexistent-page-xyz', { waitUntil: 'load' });
  await page.waitForTimeout(5000);
  
  // Close popup if present
  const closeBtn = page.locator('button[aria-label="Close"]');
  if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await closeBtn.click({ force: true });
    await page.waitForTimeout(500);
  }
  
  const bodyText = await page.locator('body').textContent();
  console.log(`\n=== 404 PAGE BODY (first 500): ${bodyText?.substring(0, 500)}`);
  
  // Check for h1
  const h1 = page.locator('h1');
  const h1Count = await h1.count();
  for (let i = 0; i < h1Count; i++) {
    console.log(`  h1: "${await h1.nth(i).textContent()}"`);
  }
  
  // Check for buttons/links
  const btns = page.locator('button, a');
  const btnCount = await btns.count();
  for (let i = 0; i < Math.min(btnCount, 15); i++) {
    const text = await btns.nth(i).textContent();
    const href = await btns.nth(i).getAttribute('href');
    console.log(`  btn/link: text="${text?.trim()?.substring(0, 50)}" href="${href}"`);
  }
  
  // Check for main
  const main = page.locator('main');
  console.log(`  main count: ${await main.count()}`);
  
  await page.screenshot({ path: 'test-results/diag-404.png', fullPage: true });
});

test('diag: account dashboard after login', async ({ page }) => {
  await page.goto('/account/login', { waitUntil: 'load' });
  await page.waitForTimeout(2000);
  
  // Close popup
  const closeBtn = page.locator('button[aria-label="Close"]');
  if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await closeBtn.click({ force: true });
    await page.waitForTimeout(500);
  }
  
  await page.locator('input[type="email"]').first().fill('testcustomer@hadha.co');
  await page.locator('input[type="password"]').first().fill('TestPassword123!');
  await page.getByRole('button', { name: /sign in/i }).click({ force: true });
  await page.waitForTimeout(5000);
  
  console.log(`\n=== AFTER LOGIN URL: ${page.url()}`);
  
  // If we're on account page, explore it
  if (page.url().includes('/account')) {
    const bodyText = await page.locator('body').textContent();
    console.log(`=== ACCOUNT PAGE BODY (first 1000): ${bodyText?.substring(0, 1000)}`);
    
    // Check for buttons
    const btns = page.locator('button');
    const btnCount = await btns.count();
    console.log(`=== ${btnCount} buttons ===`);
    for (let i = 0; i < Math.min(btnCount, 20); i++) {
      const text = await btns.nth(i).textContent();
      const ariaLabel = await btns.nth(i).getAttribute('aria-label');
      console.log(`  btn ${i}: text="${text?.trim()?.substring(0, 50)}" aria-label="${ariaLabel}"`);
    }
    
    await page.screenshot({ path: 'test-results/diag-account.png', fullPage: true });
  } else {
    console.log('Not on account page after login');
    await page.screenshot({ path: 'test-results/diag-login-failed.png', fullPage: true });
  }
});

test('diag: products page full content', async ({ page }) => {
  await page.goto('/products', { waitUntil: 'load' });
  await page.waitForTimeout(5000);
  
  // Close popup
  const closeBtn = page.locator('button[aria-label="Close"]');
  if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await closeBtn.click({ force: true });
    await page.waitForTimeout(500);
  }
  
  const bodyText = await page.locator('body').textContent();
  console.log(`\n=== PRODUCTS PAGE BODY (first 1500): ${bodyText?.substring(0, 1500)}`);
  
  // Check for any links in the page
  const allLinks = page.locator('a');
  const linkCount = await allLinks.count();
  console.log(`=== ${linkCount} total links ===`);
  for (let i = 0; i < Math.min(linkCount, 30); i++) {
    const text = await allLinks.nth(i).textContent();
    const href = await allLinks.nth(i).getAttribute('href');
    if (href && !href.startsWith('#') && text?.trim()) {
      console.log(`  link: "${text.trim().substring(0, 50)}" -> "${href}"`);
    }
  }
  
  // Check for any img
  const imgs = page.locator('img');
  const imgCount = await imgs.count();
  console.log(`=== ${imgCount} images ===`);
  
  // Check for skeleton loading
  const skeletons = page.locator('.animate-pulse, [data-skeleton]');
  const skeletonCount = await skeletons.count();
  console.log(`=== ${skeletonCount} skeleton elements ===`);
  
  await page.screenshot({ path: 'test-results/diag-products-full.png', fullPage: true });
});
