import { test, expect } from '@playwright/test';
import { mockAccount } from './account';
test('sign in keeps requested view and sign out removes the workspace', async ({ page }) => {
  await mockAccount(page, false);
  await page.goto('/#/workspace?view=Learn&sample=clean');
  await expect(page.getByRole('heading', { name: 'Your private workspace' })).toBeVisible();
  await page.getByLabel('Email', { exact: true }).fill('ui@example.invalid');
  await page.getByLabel('Password', { exact: true }).fill('mock-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.locator('#narration')).toBeVisible();
  await expect(page.getByLabel('Sample scenario')).toHaveValue('clean');
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible())
    await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your private workspace' })).toBeVisible();
  await expect(page.locator('#narration')).toHaveCount(0);
});
test('signup waits for email confirmation and cannot enter as a guest', async ({ page }) => {
  await page.route('**/auth/v1/signup*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ user: { id: 'unconfirmed' }, session: null }),
    }),
  );
  await page.goto('/#/workspace');
  await page.getByRole('button', { name: 'New here? Create an account' }).click();
  await page.getByLabel('Email', { exact: true }).fill('ui@example.invalid');
  await page.getByLabel('Password', { exact: true }).fill('mock-password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Check your email');
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Continue with the sample replay' })).toHaveCount(
    0,
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
});
test('rejected persisted session fails closed', async ({ page }) => {
  await mockAccount(page);
  await page.route('**/auth/v1/user', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ msg: 'Invalid JWT' }),
    }),
  );
  await page.goto('/#/workspace');
  await expect(page.getByRole('heading', { name: 'Your private workspace' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save run', exact: true })).toHaveCount(0);
});
