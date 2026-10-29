import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { mockAccount, user } from './account';

const sample = JSON.parse(
  readFileSync(new URL('../public/samples/skipped-cap.json', import.meta.url), 'utf8'),
);
const snapshot = {
  id: 'snapshot',
  name: 'Saved cap check',
  source_run_id: 'same-result',
  provenance: 'synthetic',
  created_at: '2026-10-29T08:00:00Z',
};
const recording = {
  id: 'recording',
  name: 'tabletop.mp4',
  object_path: `${user.id}/tabletop.mp4`,
  kind: 'held_out',
  size_bytes: 100,
  status: 'uploaded',
  created_at: '2026-10-29T12:00:00Z',
};
async function setup(page: Page, withJobs = true) {
  await mockAccount(page);
  const state = {
    runs: [{ ...snapshot }],
    recordings: [{ ...recording }],
    jobs: withJobs
      ? [
          {
            id: 'same-result',
            kind: 'run',
            status: 'ready',
            result: sample,
            created_at: '2026-10-29T13:00:00Z',
          },
          {
            id: 'protocol',
            kind: 'learn',
            status: 'ready',
            result: { protocol: { ...sample.protocol, name: 'Tube checklist' } },
            created_at: '2026-10-29T09:00:00Z',
          },
          {
            id: 'working',
            kind: 'run',
            status: 'processing',
            result: { name: 'Checking the second take' },
            created_at: '2026-10-29T10:00:00Z',
          },
          {
            id: 'failed',
            kind: 'learn',
            status: 'error',
            result: { error: 'private internal stack trace' },
            created_at: '2026-10-29T11:00:00Z',
          },
        ]
      : [],
    downloads: 0,
  };
  await page.route('**/rest/v1/**', (route) => {
    const req = route.request(),
      url = new URL(req.url());
    const reply = (data: unknown) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    if (url.pathname.endsWith('/analysis_jobs')) return reply(state.jobs);
    if (url.pathname.endsWith('/run_records'))
      return reply(url.searchParams.get('select') === 'payload' ? { payload: sample } : state.runs);
    if (url.pathname.endsWith('/rpc/delete_run_snapshot')) {
      state.runs = [];
      return reply(null);
    }
    if (url.pathname.endsWith('/recordings')) {
      if (req.method() === 'DELETE') state.recordings = [];
      if (req.method() === 'POST')
        state.recordings.push({
          ...req.postDataJSON(),
          id: 'uploaded',
          created_at: '2026-10-29T14:00:00Z',
          status: 'uploaded',
        });
      return reply(req.method() === 'GET' ? state.recordings : null);
    }
    return reply([]);
  });
  await page.route('**/storage/v1/**', (route) => {
    const req = route.request(),
      url = new URL(req.url());
    if (url.pathname.includes('/object/sign/') && req.method() === 'POST')
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          signedURL: '/object/sign/recordings/mock?token=public-test-fixture',
        }),
      });
    if (req.method() === 'GET') {
      state.downloads += 1;
      return route.fulfill({ status: 200, contentType: 'video/mp4', body: 'mock-video' });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.goto('/#/workspace?sample=skipped-cap&view=Supervise');
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  await expect(page.locator('.sample-access-banner')).toHaveCount(0);
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible())
    await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('button', { name: 'My runs', exact: true }).click();
  await expect(page.locator('.saved-run')).toHaveCount(withJobs ? 5 : 2);
  return state;
}

test('one chronological list combines work, deduplicates saved results and explains unavailable jobs', async ({
  page,
}) => {
  await setup(page);
  await expect(page.locator('.saved-run strong')).toHaveText([
    'tabletop.mp4',
    'Teaching checklist',
    'Checking the second take',
    'Tube checklist',
    'Saved cap check',
  ]);
  await expect(page.locator('.library-item-type')).toHaveText([
    'Recording',
    'Protocol',
    'Run',
    'Protocol',
    'Run',
  ]);
  await expect(
    page.getByRole('button', { name: 'Open Checking the second take', exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole('button', { name: 'Open Teaching checklist', exact: true }),
  ).toBeDisabled();
  await expect(page.getByText('Still processing. Refresh to check again.')).toBeVisible();
  await expect(
    page.getByText('Could not finish. Try uploading the recording again.'),
  ).toBeVisible();
  await expect(page.getByText('private internal stack trace')).toHaveCount(0);
  await expect(page.locator('.saved-run time')).toHaveCount(5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
  await page.getByRole('button', { name: 'Open Saved cap check', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
});

for (const action of ['Teach', 'Check'])
  test(`a private recording opens with a Use in ${action} action`, async ({ page }) => {
    const state = await setup(page, false);
    await page.getByRole('button', { name: 'Open tabletop.mp4', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'tabletop.mp4', exact: true });
    await expect(dialog.locator('video')).toBeVisible();
    await dialog.getByRole('button', { name: `Use in ${action}`, exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(action === 'Teach' ? /view=Teach/ : /view=Check/);
    expect(state.downloads).toBeGreaterThan(0);
  });

test('upload starts collapsed, uses clear roles and preserves recording/run deletion', async ({
  page,
}) => {
  const state = await setup(page, false);
  const add = page.locator('.recording-add');
  await expect(add).not.toHaveAttribute('open');
  await add.locator('summary').click();
  await expect(
    page.getByRole('button', { name: 'Upload recording', exact: true }),
  ).toHaveAccessibleDescription('Choose a recording to upload.');
  await expect(page.locator('#recording-kind option')).toHaveText([
    'Teaching video',
    'Second video',
    'New recording',
  ]);
  await page.getByLabel('Recording file').setInputFiles({
    name: 'new-take.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('test fixture'),
  });
  await page.locator('#recording-kind').selectOption('held_out');
  await page.getByRole('button', { name: 'Upload recording', exact: true }).click();
  await expect(page.locator('.saved-run').first()).toContainText('new-take.mp4');
  expect(state.recordings.at(-1)?.kind).toBe('held_out');
  expect((state.recordings.at(-1) as unknown as { owner_id: string }).owner_id).toBe(user.id);
  await page.getByRole('button', { name: 'Delete Saved cap check', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open Saved cap check', exact: true })).toHaveCount(
    0,
  );
  await page.getByRole('button', { name: 'Delete tabletop.mp4', exact: true }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Delete recording', exact: true })
    .click();
  await expect(page.getByRole('button', { name: 'Open tabletop.mp4', exact: true })).toHaveCount(0);
});
