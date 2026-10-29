import { mockAccount } from './account';
import { test, expect } from '@playwright/test';

test('homepage compares synthetic fixture results and opens the selected run', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await mockAccount(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Show it once. Check each step.' })).toBeVisible();
  await expect(page.locator('.comparison-step')).toHaveCount(4);
  await expect(page.locator('.comparison-observation')).toContainText('Step skipped');
  await page.getByRole('button', { name: 'Clean run', exact: true }).click();
  await expect(page.locator('.comparison-step.missed')).toHaveCount(0);
  await expect(page.locator('.comparison-observation')).toContainText(
    'All steps were observed in order.',
  );
  await page.getByRole('button', { name: 'Open this sample' }).click();
  await expect(page.getByRole('button', { name: 'Clean procedure', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('homepage images load and layout fits at this viewport', async ({ page }) => {
  await mockAccount(page);
  await page.goto('/');
  for (const image of await page.locator('img').all()) {
    await expect(image).toHaveAttribute('alt', /.+/);
    await image.evaluate((el) => el.scrollIntoView({ block: 'center' }));
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
      .toBeTruthy();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
  await page.getByRole('button', { name: 'Open Teach', exact: true }).click();
  await expect(page.locator('#narration')).toBeVisible();
  await page.getByRole('button', { name: 'Use the sample steps', exact: true }).click();
  await expect(page.getByText('Example', { exact: true })).toBeVisible();
  const advanced = page.getByText('Advanced details', { exact: true });
  await advanced.click();
  await expect(page.locator('pre').first()).toContainText('touching');
});

test('workspace requires sign-in and invalid credentials do not grant access', async ({ page }) => {
  await page.route('**/auth/v1/token*', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'invalid_credentials', msg: 'Invalid login credentials' }),
    }),
  );
  await page.goto('/#/workspace');
  await expect(page.getByRole('heading', { name: 'Your private workspace' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toHaveCount(0);
  await page.getByLabel('Email', { exact: true }).fill('demo@example.invalid');
  await page.getByLabel('Password', { exact: true }).fill('test-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid login credentials');
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Back to the homepage' }).click();
  await expect(page.getByRole('heading', { name: 'Show it once. Check each step.' })).toBeVisible();
});

test('scroll reveals settle once and stay visible on return', async ({ page }) => {
  await page.goto('/');
  const heading = page.getByRole('heading', { name: 'See why a step was flagged.' });
  await heading.scrollIntoViewIfNeeded();
  await expect(heading).toHaveCSS('opacity', '1');
  await expect(heading).toHaveCSS('transform', 'none');
  await page.evaluate(() => scrollTo(0, 0));
  await heading.scrollIntoViewIfNeeded();
  await expect(heading).toHaveCSS('opacity', '1');
});

test('reduced motion keeps content visible without entrance transforms', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const heading = page.getByRole('heading', { name: 'See why a step was flagged.' });
  await expect(heading).toHaveCSS('opacity', '1');
  await expect(heading).toHaveCSS('transform', 'none');
  await expect(page.locator('.hero-orbit')).toHaveCSS('transform', 'none');
});

test('first visit explains the workflow and opens a sample without an account', async ({
  page,
}) => {
  await page.route('**/api/**', (route) => route.abort());
  await page.goto('/');
  await expect(page.locator('.hero-copy')).toContainText('step-by-step checklist');
  await expect(page.locator('.hero-copy')).toContainText('missed steps');
  await expect(page.locator('.hero-caption')).toContainText('without signing in');
  await expect(page.locator('.home-note').first()).toContainText('not a real recording');
  await page
    .getByRole('button', { name: 'See it catch a mistake (30 seconds)', exact: true })
    .click();
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Example run');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
