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
  await expect(page.getByRole('slider', { name: 'Replay position' })).toHaveValue('17');
  await expect(page.locator('.why-flagged')).toBeVisible();
  await expect(page.locator('.why-flagged strong')).toHaveText('Step skipped');
  await expect(page.locator('.why-flagged p').first()).toBeInViewport();
  await expect(page.locator('.predicate-detail')).toBeVisible();
});

test('trying your own video requires sign-in', async ({ page }) => {
  await page.goto('/#/workspace?view=Home&sample=skipped-cap');
  await page.getByRole('button', { name: 'Try it with your own video' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('entry through Home reaches a selected alert in two clicks without backend access', async ({
  page,
}) => {
  const requests: string[] = [];
  await page.route('**/api/**', (route) => {
    requests.push(route.request().url());
    return route.abort();
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Open Apprentice', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Home', level: 1, exact: true })).toBeVisible();
  await page
    .getByRole('button', { name: 'See it catch a mistake (30 seconds)', exact: true })
    .click();
  await expect(page.locator('.why-flagged')).toBeVisible();
  await expect(page.locator('.why-flagged strong')).toHaveText('Step skipped');
  await expect(page.locator('.why-flagged p').first()).toBeInViewport();
  await expect(page.locator('.step.selected')).toContainText('Cap tube 1');
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  expect(requests).toEqual([]);
});

test('landing comparison and replay focus on the same finding', async ({ page }) => {
  await page.route('**/api/**', (route) => route.abort());
  await page.goto('/');
  const finding = page.locator('.comparison-observation');
  await expect(finding).toContainText('Step skipped');
  await expect(finding).toContainText('00:17');
  await page.getByRole('button', { name: 'Open this sample' }).click();
  await expect(page.locator('.why-flagged strong')).toHaveText('Step skipped');
  await expect(page.getByRole('slider', { name: 'Replay position' })).toHaveValue('17');
  await expect(page.locator('.why-flagged')).toContainText(
    'It also stayed active longer than allowed first.',
  );
  await expect(page.locator('.why-flagged [title], .timeline-events [title]')).toHaveCount(0);
});
