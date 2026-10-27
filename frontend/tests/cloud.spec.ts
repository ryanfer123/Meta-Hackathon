import { test, expect, type Page } from '@playwright/test';

// UI contract tests mock cloud HTTP. Server authorization is tested separately in supabase/tests.
test('account saves, reopens and deletes a run; private upload is retained', async ({ page }) => {
  let snapshot: any;
  let saved = false;
  let recording: any;
  const user = {
    id: '44444444-4444-4444-8444-444444444444',
    aud: 'authenticated',
    role: 'authenticated',
    email: 'ui@example.invalid',
    app_metadata: {},
    user_metadata: {},
    created_at: '2026-10-27T00:00:00Z',
  };
  const token = `${btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))}.${btoa(JSON.stringify({ sub: user.id, exp: 4102444800, role: 'authenticated' }))}.test`;
  await page.route('**/*.supabase.co/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    const reply = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.pathname.endsWith('/token'))
      return reply({
        access_token: token,
        token_type: 'bearer',
        expires_in: 3600,
        refresh_token: 'mock-refresh',
        user,
      });
    if (url.pathname.endsWith('/user')) return reply(user);
    if (url.pathname.endsWith('/rpc/save_run_snapshot')) {
      snapshot = request.postDataJSON().snapshot;
      saved = true;
      return reply('saved-run-id');
    }
    if (url.pathname.endsWith('/rpc/delete_run_snapshot')) {
      saved = false;
      return reply(null);
    }
    if (url.pathname.endsWith('/run_records'))
      return reply(
        url.searchParams.get('select') === 'payload'
          ? { payload: snapshot }
          : saved
            ? [
                {
                  id: 'saved-run-id',
                  name: snapshot.name,
                  provenance: snapshot.provenance,
                  source_run_id: snapshot.id,
                  created_at: '2026-10-27T00:00:00Z',
                },
              ]
            : [],
      );
    if (url.pathname.endsWith('/recordings') && url.pathname.startsWith('/rest/')) {
      if (request.method() === 'POST') {
        recording = {
          ...request.postDataJSON(),
          id: 'recording-id',
          created_at: '2026-10-27T00:00:00Z',
          status: 'uploaded',
        };
        return reply(null, 201);
      }
      return reply(recording ? [recording] : []);
    }
    if (url.pathname.startsWith('/storage/v1/object/'))
      return reply({ Key: 'mock-private-object' });
    return reply({ message: 'Unmocked cloud request: ' + url.pathname }, 400);
  });
  await page.goto('/#/workspace');
  const save = page.getByRole('button', { name: 'Save run', exact: true });
  await expect(save).toBeEnabled();
  await save.click();
  await page.getByLabel('Email', { exact: true }).fill(user.email);
  await page.getByLabel('Password', { exact: true }).fill('mock-password');
  const signin = page.getByRole('dialog').getByRole('button', { name: 'Sign in', exact: true });
  test.skip(
    !(await signin.isEnabled()),
    'Cloud client not configured in this standalone installation',
  );
  await signin.click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await save.click();
  await expect(page.locator('.toast')).toContainText('Run saved');
  await view(page, 'Run library');
  await expect(page.locator('.saved-run')).toHaveCount(1);
  await page.getByRole('button', { name: 'Open run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  await view(page, 'Run library');
  await page.getByRole('button', { name: `Delete ${snapshot.name}`, exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete run', exact: true }).click();
  await expect(page.getByText('No saved runs yet.', { exact: false })).toBeVisible();
  await page.getByLabel('Recording file').setInputFiles({
    name: 'expert.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('synthetic-upload-fixture'),
  });
  await page.getByRole('button', { name: 'Upload recording', exact: true }).click();
  await expect(page.getByText('expert.mp4', { exact: true })).toBeVisible();
  await expect.poll(() => recording?.owner_id).toBe(user.id);
  expect(recording.object_path).toMatch(new RegExp('^' + user.id + '/'));
  await expect(page.getByText('Uploaded, analysis pending', { exact: false })).toBeVisible();
});

async function view(page: Page, name: string) {
  const button = page
    .getByRole('navigation', { name: 'Workspace' })
    .getByRole('button', { name, exact: true });
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible())
    await page.getByRole('button', { name: 'Open navigation' }).click();
  await button.click();
}
