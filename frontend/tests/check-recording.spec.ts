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
          health: { replay_mode: !enabled, live_configured: enabled },
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

test('Check exposes a disabled reason and uses the shared upload/poll path', async ({ page }) => {
  let uploaded = false;
  await page.route('**/api/runs', (route) => {
    uploaded =
      route.request().method() === 'POST' &&
      !!route.request().postDataBuffer()?.includes(Buffer.from('mock-procedure'));
    return route.fulfill({ json: { run_id: 'mock-run' } });
  });
  await page.route('**/api/runs/mock-run', (route) => route.fulfill({ json: { status: 'ready' } }));
  const target = await mountCheck(page);
  const button = target.getByRole('button', { name: 'Check this recording' });
  await expect(button).toBeDisabled();
  await expect(button).toHaveAccessibleDescription('Add a recording to continue.');
  await target.getByLabel('New recording', { exact: true }).setInputFiles({
    name: 'new.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('synthetic-input-fixture'),
  });
  await button.click();
  await expect(target).toHaveAttribute('data-finished', 'yes');
  expect(uploaded).toBeTruthy();
});

test('Check explains unavailable analysis', async ({ page }) => {
  const target = await mountCheck(page, false);
  const button = target.getByRole('button', { name: 'Check this recording' });
  await expect(button).toBeDisabled();
  await expect(button).toHaveAccessibleDescription(/Analysis isn't connected here/);
});
