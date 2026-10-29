import { test, expect } from '@playwright/test';
import { mockAccount } from './account';
test('example timings cannot be submitted as real validation', async ({ page }) => {
  await mockAccount(page);
  await page.goto('/#/workspace?sample=skipped-cap&view=Teach');
  await page.getByRole('button', { name: 'Use the sample steps', exact: true }).click();
  await expect(page.locator('textarea')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Run the checks', exact: true })).toHaveCount(0);
  await expect(page.getByText('Example', { exact: true })).toBeVisible();
  await expect(page.locator('.validation-checks')).toHaveCount(0);
});
