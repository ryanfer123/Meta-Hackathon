import { mockAccount } from './account';
import { test, expect } from '@playwright/test';

test('homepage compares real fixture results and opens the selected run', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await mockAccount(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Good work. Worth repeating.' })).toBeVisible();
  await expect(page.locator('.comparison-step')).toHaveCount(4);
  await expect(page.locator('.comparison-observation')).toContainText(
    'Cap tube 1 was not observed.',
  );
  await page.getByRole('button', { name: 'Clean run', exact: true }).click();
  await expect(page.locator('.comparison-step.missed')).toHaveCount(0);
  await expect(page.locator('.comparison-observation')).toContainText(
    'Every step was observed in order.',
  );
  await page.getByRole('button', { name: 'Inspect this run' }).click();
  await expect(page.getByLabel('Sample scenario')).toHaveValue('clean');
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('homepage images load and layout fits at this viewport', async ({ page }) => {
  await mockAccount(page);
  await page.goto('/');
  for (const image of await page.locator('img').all()) {
    await image.evaluate((el) => el.scrollIntoView({ block: 'center' }));
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
      .toBeTruthy();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
  await page.getByRole('button', { name: 'Open learn workspace', exact: true }).click();
  await expect(page.locator('#narration')).toBeVisible();
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
  await expect(page.getByRole('heading', { name: 'Good work. Worth repeating.' })).toBeVisible();
});
