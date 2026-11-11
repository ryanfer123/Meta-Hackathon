import { test, expect, type Page } from '@playwright/test';
import { mockAccount } from './account';

async function mountCheck(page: Page, enabled = true) {
  await mockAccount(page);
  await page.goto('/');
  const run = await page.request.get('/samples/skipped-cap.json').then((r) => r.json());
  await page.evaluate(
    async ({ run, enabled }) => {
      const load = new Function('path', 'return import(path)') as (p: string) => Promise<any>;
      const [react, dom, component] = await Promise.all([
        load('/node_modules/.vite/deps/react.js'),
        load('/node_modules/.vite/deps/react-dom_client.js'),
        load('/src/pages/Check.tsx'),
      ]);
      document.getElementById('root')!.style.display = 'none';
      const target = document.createElement('main');
      target.id = 'check-test';
      document.body.append(target);
      (dom.default ?? dom).createRoot(target).render(
        (react.default ?? react).createElement(component.CheckRecording, {
          procedure: { id: 'mock-procedure', protocol: run.protocol },
          health: { replay_mode: !enabled, live_configured: enabled, max_run_duration_s: 300 },
          onTeach: () => {},
          onSample: () => {},
          onSignIn: () => {},
          onRun: () => {
            target.dataset.finished = 'yes';
          },
        }),
      );
    },
    { run, enabled },
  );
  return page.locator('#check-test');
}

test('Check explains its prerequisite without an upload', async ({ page }) => {
  await page.goto('/#/workspace?view=Check&sample=skipped-cap');
  await expect(page.getByRole('heading', { name: 'First teach it a procedure' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Go to Teach' })).toBeVisible();
  await expect(page.locator('.check-page input[type=file]')).toHaveCount(0);
});

test('Check exposes a disabled reason and sends the per-run faster tracking choice', async ({
  page,
}) => {
  let uploaded = false;
  await page.route('**/api/runs', (route) => {
    uploaded =
      route.request().method() === 'POST' &&
      !!route.request().postDataBuffer()?.includes(Buffer.from('mock-procedure')) &&
      !!route
        .request()
        .postDataBuffer()
        ?.includes(Buffer.from('name="tracking_mode"\r\n\r\nvideo'));
    return route.fulfill({ json: { run_id: 'mock-run' } });
  });
  await page.route('**/api/runs/mock-run', (route) => route.fulfill({ json: { status: 'ready' } }));
  const target = await mountCheck(page);
  const button = target.getByRole('button', { name: 'Check this recording' });
  await expect(button).toBeDisabled();
  await expect(button).toHaveAccessibleDescription('Add a recording to continue.');
  await expect(
    target.getByText('Choose MP4 / MOV · up to 90 seconds', { exact: true }),
  ).toBeVisible();
  const faster = target.getByRole('checkbox', { name: 'Faster video tracking (preview)' });
  await expect(faster).not.toBeChecked();
  await expect(faster).toHaveAccessibleDescription(/same spending limit/);
  await faster.check();
  await expect(
    target.getByText('Choose MP4 / MOV · up to 300 seconds', { exact: true }),
  ).toBeVisible();
  await expect(faster).toHaveAccessibleDescription(/up to 300 seconds/);
  await target.getByLabel('New recording', { exact: true }).setInputFiles({
    name: 'new.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('synthetic-input-fixture'),
  });
  await button.click();
  await expect(target).toHaveAttribute('data-finished', 'yes');
  await expect(faster).toBeChecked();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
  if (process.env.APPRENTICE_UI_CAPTURE)
    await page.screenshot({
      path: `/tmp/apprentice-tracking-choice-${test.info().project.name}.png`,
    });
  expect(uploaded).toBeTruthy();
});

test('Check explains unavailable analysis', async ({ page }) => {
  const target = await mountCheck(page, false);
  const button = target.getByRole('button', { name: 'Check this recording' });
  await expect(button).toBeDisabled();
  await expect(button).toHaveAccessibleDescription(/Analysis isn't connected here/);
});

test('object preview stays separate from a full check and reuses the uploaded job', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const target = await mountCheck(page);
  const sample = await page.request.get('/samples/skipped-cap.json').then((r) => r.json());
  const preview = {
    id: 'preview-job',
    status: 'ready',
    phase: 'object-preview',
    protocol: sample.protocol,
    frames: sample.frames.slice(0, 3).map((f: any) => ({
      ...f,
      image:
        'data:image/svg+xml;base64,' +
        Buffer.from(
          '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#e9e0ce"/><text x="20" y="35" font-family="sans-serif" fill="#183247">UI test fixture · no real recording</text></svg>',
        ).toString('base64'),
    })),
    objects: sample.protocol.objects.map((o: any) => ({
      name: o.name,
      visible_frames: 1,
      total_frames: 3,
    })),
  };
  let checked = false;
  await page.route('**/api/runs', (route) => {
    expect(route.request().postDataBuffer()?.toString()).toContain('name="preview_only"');
    return route.fulfill({ json: { run_id: 'preview-job' } });
  });
  await page.route('**/api/runs/preview-job', (route) =>
    route.fulfill({ json: checked ? { ...sample, status: 'ready' } : preview }),
  );
  await page.route('**/api/runs/preview-job/analyse', (route) => {
    const body = route.request().postDataBuffer()?.toString() ?? '';
    expect(body).toContain('bright red marked object');
    expect(body).toContain('name="tracking_mode"');
    expect(body).not.toContain('name="video"');
    checked = true;
    return route.fulfill({ json: { run_id: 'preview-job' } });
  });
  await target
    .getByLabel('New recording', { exact: true })
    .setInputFiles({ name: 'clip.mp4', mimeType: 'video/mp4', buffer: Buffer.from('test only') });
  await target.getByRole('button', { name: 'Preview objects (paid)', exact: true }).click();
  await expect(
    target.getByRole('heading', { name: 'Check the objects before a full run' }),
  ).toBeVisible();
  await expect(target.getByRole('img', { name: 'Object mask outlines' })).toBeVisible();
  await expect(target).not.toHaveAttribute('data-finished', 'yes');
  await target
    .getByLabel(`Description for ${sample.protocol.objects[0].name}`)
    .fill('bright red marked object');
  await target.getByRole('button', { name: 'Preview frame 2' }).click();
  await expect(target.getByRole('button', { name: 'Preview frame 2' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await expect(target.locator('.preview-objects')).toHaveCSS('display', 'grid');
  if (process.env.APPRENTICE_UI_CAPTURE)
    await page.screenshot({
      path: `/tmp/apprentice-object-preview-${test.info().project.name}.png`,
      fullPage: true,
    });
  await target.getByRole('button', { name: 'Check this recording' }).click();
  await expect(target).toHaveAttribute('data-finished', 'yes');
  expect(errors).toEqual([]);
});

test('a selected section is validated and sent using original timestamps', async ({ page }) => {
  const target = await mountCheck(page);
  await target
    .getByLabel('New recording', { exact: true })
    .setInputFiles({ name: 'long.mp4', mimeType: 'video/mp4', buffer: Buffer.from('test only') });
  await target.getByText('Trim new recording to the procedure (optional)', { exact: true }).click();
  await target.getByLabel('New recording section preview').evaluate((v) => {
    Object.defineProperty(v, 'duration', { value: 180, configurable: true });
    v.dispatchEvent(new Event('loadedmetadata'));
  });
  await target.getByRole('checkbox', { name: 'Choose a section of new recording' }).check();
  await target.getByLabel('New recording section start', { exact: true }).fill('20');
  await target.getByLabel('New recording section end', { exact: true }).fill('30');
  await expect(target.getByRole('status')).toContainText('10.0 seconds selected');
  await target.getByLabel('New recording section end', { exact: true }).fill('19');
  await expect(target.getByRole('button', { name: 'Check this recording' })).toBeDisabled();
  await target.getByLabel('New recording section end', { exact: true }).fill('30');
  await page.route('**/api/runs', (route) => {
    const body = route.request().postDataBuffer()?.toString() ?? '';
    expect(body).toContain('name="trim_start_s"\r\n\r\n20');
    expect(body).toContain('name="trim_end_s"\r\n\r\n30');
    return route.fulfill({ json: { run_id: 'trimmed' } });
  });
  await page.route('**/api/runs/trimmed', (route) => route.fulfill({ json: { status: 'ready' } }));
  await target.getByRole('button', { name: 'Check this recording' }).click();
  await expect(target).toHaveAttribute('data-finished', 'yes');
});
