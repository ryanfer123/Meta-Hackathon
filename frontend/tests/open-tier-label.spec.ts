import { test, expect } from '@playwright/test';

test('configured open-model label appears in Audit and Supervise', async ({ page }) => {
  await page.route('**/samples/skipped-cap.json', async (route) => {
    const response = await route.fetch();
    const run = await response.json();
    run.metrics.open_tier_label = 'spark-open';
    run.events.push({
      t: 0,
      step_id: 'approach',
      kind: 'uncertain',
      tier: 'glimmer',
      confidence: 0.5,
      detail: 'Mock open-model advisory label check',
      evidence_frame: null,
    });
    await route.fulfill({ json: run });
  });
  await page.goto('/#/workspace?sample=skipped-cap&view=Audit');
  await expect(page.locator('.tier').filter({ hasText: 'spark-open' })).toBeVisible();
  await expect(page.locator('.tier').filter({ hasText: /^glimmer$/ })).toHaveCount(0);
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible())
    await page.getByRole('button', { name: 'Open navigation' }).click();
  await page
    .getByRole('navigation', { name: 'Workspace' })
    .getByRole('button', { name: 'Supervise', exact: true })
    .click();
  await expect(page.locator('.tier').filter({ hasText: 'spark-open' })).toBeVisible();
  await expect(page.locator('.tier').filter({ hasText: /^glimmer$/ })).toHaveCount(0);
});
