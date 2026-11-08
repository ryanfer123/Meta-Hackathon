import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

test('offline labelling checks the source hash and exports explicit labels without predictions or API calls', async ({
  page,
}) => {
  const bytes = Buffer.from('test-only media placeholder');
  const payload = {
    manifest: {
      runs: [
        {
          id: 'test-take',
          split: 'test',
          source: 'real',
          filename: 'take.mp4',
          video_sha256: createHash('sha256').update(bytes).digest('hex'),
          events: [],
          labels_confirmed: false,
        },
      ],
    },
    steps: [{ id: 'cap', title: 'Replace cap' }],
  };
  const template = readFileSync(
    new URL('../../scripts/label_template.html', import.meta.url),
    'utf8',
  );
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  let apiCalls = 0;
  await page.route('**/api/**', (r) => {
    apiCalls++;
    return r.abort();
  });
  await page.route('**/__labels', (r) =>
    r.fulfill({
      contentType: 'text/html',
      body: template.replace('PAYLOAD', JSON.stringify(payload).replaceAll('<', '\\u003c')),
    }),
  );
  await page.goto('/__labels');
  await expect(page).toHaveTitle('Blind recording labels');
  await expect(
    page.getByRole('heading', { name: 'Label recordings before viewing predictions' }),
  ).toBeVisible();
  await page
    .locator('#file')
    .setInputFiles({ name: 'wrong.mp4', mimeType: 'video/mp4', buffer: Buffer.from('different') });
  await expect(page.getByRole('status')).toHaveText('This file does not match the manifest.');
  await expect(page.locator('#confirm')).toBeDisabled();
  await page
    .locator('#file')
    .setInputFiles({ name: 'take.mp4', mimeType: 'video/mp4', buffer: bytes });
  await expect(page.getByRole('status')).toHaveText('Matched take.mp4');
  await page.locator('#video').evaluate((v) => {
    Object.defineProperty(v, 'duration', { value: 10, configurable: true });
    Object.defineProperty(v, 'currentTime', { value: 3.2, writable: true });
    v.dispatchEvent(new Event('loadedmetadata'));
  });
  await page.getByRole('button', { name: 'Add finding at current time' }).click();
  await expect(page.locator('#events')).toContainText('3.20s · skipped · cap');
  await expect(page.getByRole('button', { name: 'Download confirmed labels' })).toBeDisabled();
  await page.locator('#confirm').check();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download confirmed labels' }).click();
  expect((await download).suggestedFilename()).toBe('labels.confirmed.json');
  expect(apiCalls).toBe(0);
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});
