import { test, expect } from '@playwright/test';

for (const [view, expected, tab] of [
  ['Home', 'Home', ''],
  ['Teach', 'Teach', ''],
  ['Supervise', 'Results', 'Replay'],
  ['Audit', 'Results', 'Integrity'],
  ['Results&tab=Integrity', 'Results', 'Integrity'],
]) {
  test(`legacy and current route ${view} stays usable`, async ({ page }) => {
    await page.goto(`/#/workspace?view=${view}&sample=skipped-cap`);
    await expect(
      page.getByRole('heading', { name: expected, exact: true, level: 1 }),
    ).toBeVisible();
    if (tab)
      await expect(page.getByRole('tab', { name: tab, exact: true })).toHaveAttribute(
        'aria-selected',
        'true',
      );
    await expect(page.getByLabel('Sample scenario')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save run', exact: true })).toHaveCount(0);
  });
}

test('sidebar has four destinations and My runs stays an account action', async ({ page }) => {
  await page.goto('/#/workspace?view=Home&sample=skipped-cap');
  await expect(page.locator('.workspace-topbar')).toBeVisible();
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible())
    await page.getByRole('button', { name: 'Open navigation' }).click();
  const nav = page.getByRole('navigation', { name: 'Workspace' });
  await expect(nav.getByRole('button')).toHaveText(['Home', 'Teach', 'Check', 'Results']);
  await page.getByRole('button', { name: 'My runs', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});
