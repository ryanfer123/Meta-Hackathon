import { test, expect } from '@playwright/test';
import { mockAccount } from './account';

test('Home explains real work and opens Teach without adding sample data', async ({ page }) => {
  await mockAccount(page);
  await page.goto('/#/workspace?view=Home');
  await expect(
    page.getByRole('heading', { name: 'Your next procedure starts here.' }),
  ).toBeVisible();
  await expect(page.locator('.how-strip article')).toHaveCount(3);
  await expect(page.locator('.overview-page img')).toHaveCount(0);
  await page.getByRole('button', { name: 'Teach a procedure' }).click();
  await expect(page.getByLabel('Teaching video', { exact: true })).toBeVisible();
  expect(page.url()).not.toContain('sample=');
  await expect(page.getByRole('button', { name: 'Use the sample steps' })).toHaveCount(0);
});

test('signed-out legacy Home still asks for sign-in to teach', async ({ page }) => {
  await page.goto('/#/workspace?view=Home&sample=skipped-cap');
  await page.getByRole('button', { name: 'Teach a procedure' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('normal Results is empty until a recording is checked', async ({ page }) => {
  const samples: string[] = [];
  await mockAccount(page);
  page.on('request', (r) => {
    if (r.url().includes('/samples/')) samples.push(r.url());
  });
  await page.goto('/#/workspace?view=Results');
  await expect(page.getByRole('heading', { name: 'Your results will appear here' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Play replay' })).toHaveCount(0);
  await expect(page.getByText('Animated example', { exact: false })).toHaveCount(0);
  await page.getByRole('button', { name: 'Check a recording', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'First teach it a procedure' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Use the sample steps' })).toHaveCount(0);
  expect(samples).toEqual([]);
});

test('legacy sample deep links retain honest labels, focus and static verification', async ({
  page,
}) => {
  await page.route('**/api/**', (route) => route.abort());
  await page.goto('/#/workspace?view=Supervise&sample=skipped-cap');
  await expect(page.locator('.why-flagged strong')).toHaveText('Step skipped');
  await expect(page.getByRole('slider', { name: 'Replay position' })).toHaveValue('17');
  await expect(page.getByRole('note')).toContainText('Example run');
  await expect(page.locator('.why-flagged')).toContainText(
    'It also stayed active longer than allowed first.',
  );
  await page.getByRole('tab', { name: 'Integrity', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Report unchanged');
});
