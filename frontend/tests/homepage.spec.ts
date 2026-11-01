import { mockAccount } from './account';
import { test, expect } from '@playwright/test';

test('homepage leads to real teaching without requesting a sample', async ({ page }) => {
  const errors: string[] = [];
  const samples: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (r) => {
    if (r.url().includes('/samples/')) samples.push(r.url());
  });
  await mockAccount(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Show it once. Check each step.' })).toBeVisible();
  await expect(page.locator('.comparison-scene,.scene')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: /sample|example|clean run|skipped cap/i }),
  ).toHaveCount(0);
  await page.locator('.hero-copy').getByRole('button', { name: 'Teach a procedure' }).click();
  await expect(page).toHaveURL(/view=Teach/);
  expect(page.url()).not.toContain('sample=');
  await expect(page.getByLabel('Teaching video', { exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Use the sample steps' })).toHaveCount(0);
  expect(samples).toEqual([]);
  expect(errors).toEqual([]);
});

test('homepage screenshots load and layout fits at this viewport', async ({ page }) => {
  await mockAccount(page);
  await page.goto('/');
  for (const image of await page.locator('img').all()) {
    await expect(image).toHaveAttribute('alt', /.+/);
    await image.scrollIntoViewIfNeeded();
    await expect
      .poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0))
      .toBeTruthy();
    await expect(image).not.toHaveAttribute('src', /procedure-studio/);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
  await page.getByRole('button', { name: 'Open Teach', exact: true }).click();
  await expect(page.locator('#narration')).toBeVisible();
  await expect(page.getByText('Recording tips', { exact: true })).toBeVisible();
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
  await expect(page.locator('.hero-product')).toHaveCSS('transform', 'none');
});

test('first visit explains the workflow and requires an account for recordings', async ({
  page,
}) => {
  await page.route('**/api/**', (route) => route.abort());
  await page.goto('/');
  await expect(page.locator('.hero-copy')).toContainText('step-by-step checklist');
  await expect(page.locator('.hero-copy')).toContainText('missed steps');
  await page.locator('.hero-copy').getByRole('button', { name: 'Teach a procedure' }).click();
  await expect(page.getByRole('heading', { name: 'Your private workspace' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Play replay' })).toHaveCount(0);
});
