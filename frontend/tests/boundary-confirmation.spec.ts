import { test, expect } from '@playwright/test';
import { mockAccount } from './account';

test('validation requires timing review and editing a range clears confirmation', async ({
  page,
}) => {
  await mockAccount(page);
  await page.goto('/#/workspace?sample=skipped-cap&view=Learn');
  const confirmed = page.getByRole('checkbox', {
    name: 'I checked every start and end against the video and filled any missing times',
  });
  await expect(confirmed).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Run four validation checks' })).toBeDisabled();
  await confirmed.check();
  await expect(confirmed).toBeChecked();
  await page.locator('#ranges').fill('{"cap":{"start":2,"end":4}}');
  await expect(confirmed).not.toBeChecked();
  await expect(page.locator('.learn-input')).toContainText('suggest timings from its narration');
});
