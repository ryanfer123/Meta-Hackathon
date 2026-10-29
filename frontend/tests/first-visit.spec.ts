import { test, expect } from '@playwright/test';

test('Home explains the product and reaches a paused alert in one click', async ({ page }) => {
  await page.route('**/api/**', (route) => route.abort());
  await page.goto('/#/workspace?view=Home&sample=skipped-cap');
  await expect(
    page.getByRole('heading', {
      name: 'Catches missed steps in hands-on procedures, automatically.',
    }),
  ).toBeVisible();
  await expect(page.locator('.how-strip article')).toHaveCount(3);
  await expect(page.locator('.overview-page')).toContainText('no model ran for them');
  await page.getByRole('button', { name: 'See it catch a mistake (30 seconds)' }).click();
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  await expect(page.getByRole('slider', { name: 'Replay position' })).not.toHaveValue('0');
  await expect(page.locator('.why-flagged')).toBeVisible();
  await expect(page.locator('.predicate-detail')).toBeVisible();
});

test('trying your own video requires sign-in', async ({ page }) => {
  await page.goto('/#/workspace?view=Home&sample=skipped-cap');
  await page.getByRole('button', { name: 'Try it with your own video' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});
