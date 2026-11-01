import { test, expect } from '@playwright/test';
import { mockAccount } from './account';

test('beige is default; dark mode persists through reload and sign-in entry', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect(
    await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--sand').trim(),
    ),
  ).toBe('#e6dbc7');
  await page.getByRole('button', { name: 'Switch to dark mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('.home-page')).toHaveCSS('background-color', 'rgb(8, 10, 14)');
  await expect(page.getByRole('button', { name: 'Switch to light mode' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('apprentice-theme')))
    .toBe('dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: 'Open Apprentice', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your private workspace' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: 'Switch to light mode' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect(errors).toEqual([]);
});

test('workspace theme switching preserves form input and readable controls', async ({ page }) => {
  await mockAccount(page);
  await page.goto('/#/workspace?view=Teach');
  const field = page.getByLabel('Describe what happens (optional)');
  await field.fill('Keep this description while switching themes.');
  await page.getByRole('button', { name: 'Switch to dark mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(field).toHaveValue('Keep this description while switching themes.');
  await expect(field).toHaveCSS('color', 'rgb(239, 235, 227)');
  await expect(field).toHaveCSS('background-color', 'rgb(12, 16, 22)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
});

test('preview tilt responds to fine pointers and settles on leave', async ({ page }, info) => {
  test.skip(info.project.name === 'mobile', 'Pointer tilt is deliberately disabled for touch');
  await page.goto('/');
  const preview = page.locator('.hero-product');
  await expect(preview).toHaveCSS('opacity', '1');
  const before = await preview.evaluate((el) => getComputedStyle(el).transform);
  const box = (await preview.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.2);
  await expect
    .poll(() => preview.evaluate((el) => getComputedStyle(el).transform))
    .not.toBe(before);
  await page.mouse.move(0, 0);
  await expect.poll(() => preview.evaluate((el) => getComputedStyle(el).transform)).toBe(before);
});

test('reduced motion keeps the headline visible and disables preview transforms', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Show it once. Check each step.' })).toBeVisible();
  const preview = page.locator('.hero-product');
  await expect(preview).toHaveCSS('transform', 'none');
  const box = (await preview.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.2);
  await page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  );
  await expect(preview).toHaveCSS('transform', 'none');
  await expect(page.locator('.hero-line>span').first()).toHaveCSS('transform', 'none');
});
