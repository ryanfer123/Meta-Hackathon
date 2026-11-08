import { test, expect } from '@playwright/test';
import { mockAccount } from './account';

test('capture current product screens without example recordings', async ({ page }, testInfo) => {
  test.skip(
    process.env.CAPTURE_PRODUCT !== '1' || testInfo.project.name !== 'desktop',
    'Explicit documentation capture only',
  );
  await mockAccount(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1505, height: 1045 });
  await page.route('**/api/health', (route) =>
    route.fulfill({
      json: {
        replay_mode: false,
        live_configured: true,
        glimmer_configured: false,
        max_upload_bytes: 104857600,
        max_cloud_source_bytes: 94371840,
      },
    }),
  );
  await page.route('**/rest/v1/**', (route) => route.fulfill({ json: [] }));
  const shots: [string, string][] = [
    ['Teach', 'learn'],
    ['Check', 'check'],
  ];
  for (const theme of ['light', 'dark']) {
    await page.goto('/');
    await page.getByRole('button', { name: /Switch to .* mode/ }).waitFor();
    if ((await page.locator('html').getAttribute('data-theme')) !== theme) {
      await page.getByRole('button', { name: `Switch to ${theme} mode` }).click();
    }
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem('apprentice-theme')))
      .toBe(theme);
    const suffix = theme === 'dark' ? '-dark' : '';
    for (const [view, name] of shots) {
      if (theme === 'dark' && !['learn', 'check'].includes(name)) continue;
      await page.goto(`/#/workspace?view=${view}`);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(page.locator('.workspace-topbar')).toBeVisible();
      await expect(page.locator('.loading')).toHaveCount(0);
      await expect(page.locator('.workspace-view')).toHaveCSS('opacity', '1');
      await page.evaluate(() => document.fonts.ready);
      if (name === 'learn') {
        await expect(page.getByLabel('Teaching video', { exact: true })).toBeVisible();
        await expect(
          page.getByRole('button', { name: 'Create the steps' }),
        ).toHaveAccessibleDescription('Add a video to continue.');
      }
      await page.screenshot({
        path: `public/images/product-${name}${suffix}.png`,
        animations: 'disabled',
      });
    }
    await page.goto('/');
    await expect(page.locator('.hero-product img')).toBeVisible();
    await page.waitForFunction(() => {
      const image = document.querySelector('.hero-product img') as HTMLImageElement;
      return image?.complete && image.naturalWidth > 0;
    });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: `public/images/product-home${suffix}.png`,
      animations: 'disabled',
    });
  }
});
