import { test, expect } from '@playwright/test';
import { mockAccount } from './account';
test('public Learn requires sign-in for uploads and sign-out returns to a clean sample', async ({
  page,
}) => {
  await mockAccount(page, false);
  await page.goto('/#/workspace?view=Learn&sample=clean');
  await expect(
    page.getByText('Synthetic sample — sign in to analyse your own recordings'),
  ).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign in to upload a recording' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByLabel('Email', { exact: true }).fill('ui@example.invalid');
  await page.getByLabel('Password', { exact: true }).fill('mock-password');
  await page.getByRole('dialog').getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.locator('#narration')).toBeVisible();
  await page.locator('#narration').fill('private narration must be cleared on sign-out');
  await expect(page.getByLabel('Sample scenario')).toHaveValue('clean');
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible())
    await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(
    page.getByText('Synthetic sample — sign in to analyse your own recordings'),
  ).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('#narration')).toHaveCount(0);
  await expect(page.getByText('private narration must be cleared on sign-out')).toHaveCount(0);
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

for (const query of [
  'sample=unknown&view=Supervise',
  'sample=clean&view=Run%20library',
  'sample=clean&view=Overview',
]) {
  test(`private or unknown workspace route requires auth: ${query}`, async ({ page }) => {
    await page.goto('/#/workspace?' + query);
    await expect(page.getByRole('heading', { name: 'Your private workspace' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toHaveCount(0);
  });
}

test('public replay runs fully static with API blocked and private actions ask for sign-in', async ({
  page,
}) => {
  const apiRequests: string[] = [];
  const cloudRequests: string[] = [];
  await page.route('**/api/**', (route) => {
    apiRequests.push(route.request().url());
    return route.abort();
  });
  await page.route('**/*.supabase.co/**', (route) => {
    cloudRequests.push(route.request().url());
    return route.abort();
  });
  await page.goto('/#/workspace?sample=skipped-cap&view=Supervise');
  await expect(
    page.getByText('Synthetic sample — sign in to analyse your own recordings'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Seek to skipped', exact: true }).click();
  await page.locator('.step').filter({ hasText: 'Cap tube 1' }).click();
  await expect(page.locator('.predicate-detail')).toContainText('touching');
  await page.getByRole('button', { name: 'Open audit', exact: true }).first().click();
  await page.getByRole('button', { name: 'Verify chain', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Chain matches' })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign in to load your own chain' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Close sign-in', exact: true }).click();
  await page.getByRole('button', { name: 'Save run', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Close sign-in', exact: true }).click();
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible())
    await page.getByRole('button', { name: 'Open navigation' }).click();
  await page
    .getByRole('navigation', { name: 'Workspace' })
    .getByRole('button', { name: 'Run library', exact: true })
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.locator('.saved-run')).toHaveCount(0);
  await page.getByRole('button', { name: 'Close sign-in', exact: true }).click();
  for (const sample of [
    'clean',
    'skipped-cap',
    'wrong-tube',
    'swapped-order',
    'slow-action',
    'occlusion',
  ]) {
    await page.getByLabel('Sample scenario').selectOption(sample);
    await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  }
  expect(apiRequests).toEqual([]);
  expect(cloudRequests).toEqual([]);
});
