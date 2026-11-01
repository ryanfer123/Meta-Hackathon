import { test, expect } from '@playwright/test';
import { mockAccount } from './account';

test('capture current product screens without example recordings', async ({ page }, testInfo) => {
  test.skip(
    process.env.CAPTURE_PRODUCT !== '1' || testInfo.project.name !== 'desktop',
    'Explicit documentation capture only',
  );
  await mockAccount(page);
  await page.setViewportSize({ width: 1505, height: 1045 });
  await page.route('**/api/health', (route) =>
    route.fulfill({
      json: { replay_mode: false, live_configured: true, glimmer_configured: false },
    }),
  );
  await page.route('**/rest/v1/**', (route) => route.fulfill({ json: [] }));
  const shots: [string, string][] = [
    ['Teach', 'learn'],
    ['Check', 'check'],
    ['Results', 'supervise'],
    ['Results&tab=Integrity', 'audit'],
    ['Home', 'workspace'],
  ];
  for (const [view, name] of shots) {
    await page.goto(`/#/workspace?view=${view}`);
    await expect(page.locator('.workspace-topbar')).toBeVisible();
    await expect(page.locator('.loading')).toHaveCount(0);
    await page.evaluate(() => document.fonts.ready);
    if (name === 'learn') {
      await expect(page.getByLabel('Teaching video', { exact: true })).toBeVisible();
      await expect(
        page.getByRole('button', { name: 'Create the steps' }),
      ).toHaveAccessibleDescription('Add a video to continue.');
    }
    await expect(page.locator('svg[aria-label="Procedure scene"]')).toHaveCount(0);
    await page.screenshot({ path: `public/images/product-${name}.png`, animations: 'disabled' });
  }
  await page.goto('/');
  await expect(page.locator('.hero-product img')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: 'public/images/product-home.png', animations: 'disabled' });
});
