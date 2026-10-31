import { test, expect, type Page } from '@playwright/test';
import type { Run } from '../src/types';

async function mountResults(
  page: Page,
  options: {
    tab?: 'Replay' | 'Integrity';
    changeEvent?: boolean;
    live?: boolean;
    noMetrics?: boolean;
    openCall?: boolean;
    cryptoUnavailable?: boolean;
    advisory?: boolean;
  } = {},
) {
  await page.route('**/api/**', (route) => route.abort());
  await page.goto('/');
  const run = (await page.request
    .get('/samples/skipped-cap.json')
    .then((response) => response.json())) as Run;
  if (options.changeEvent) run.events[0].detail = 'Changed report text';
  if (options.advisory)
    run.events.push({
      t: 17,
      step_id: 'cap',
      kind: 'uncertain',
      tier: 'glimmer',
      confidence: 0.9,
      evidence_frame: null,
      detail: 'The final shape proves all steps happened in order.',
    });
  if (options.live) {
    run.provenance = 'live-recording';
    Object.assign(
      run.metrics,
      options.noMetrics
        ? {}
        : {
            open_tier_label: 'spark-open',
            calls: [
              { tier: 'spark', model: 'muse-spark-1.3', latency_ms: 1000, cloud_frames: 1 },
              { tier: 'sam', model: 'sam-3.1', latency_ms: 3000, cloud_frames: 4 },
            ],
            shadow_opinions_requested: 7,
          },
    );
    // A request count is not an available second opinion; the open chip must not be invented.
  }
  if (options.openCall)
    (run.metrics as any).calls.push({
      tier: 'spark-open',
      model: 'meta-models/muse-spark-open-1026',
      latency_ms: 500,
    });
  await page.evaluate(
    async ({ run, tab, cryptoUnavailable }) => {
      if (cryptoUnavailable)
        Object.defineProperty(crypto, 'subtle', {
          value: { digest: () => Promise.reject(new Error('mock crypto unavailable')) },
          configurable: true,
        });
      const load = new Function('path', 'return import(path)') as (
        path: string,
      ) => Promise<Record<string, unknown>>;
      const [react, dom, components] = await Promise.all([
        load('/node_modules/.vite/deps/react.js'),
        load('/node_modules/.vite/deps/react-dom_client.js'),
        load('/src/Results.tsx'),
      ]);
      const oldRoot = document.getElementById('root');
      if (oldRoot) oldRoot.style.display = 'none';
      const target = document.createElement('main');
      target.id = 'results-test';
      target.style.cssText = 'padding:20px;max-width:1400px;margin:auto';
      document.body.append(target);
      const createElement = ((react.default ?? react) as Record<string, unknown>).createElement as (
        ...args: unknown[]
      ) => unknown;
      const createRoot = ((dom.default ?? dom) as Record<string, unknown>).createRoot as (
        target: HTMLElement,
      ) => {
        render: (element: unknown) => void;
      };
      createRoot(target).render(
        createElement(components.Results, { run, initialTab: tab, readOnly: true }),
      );
    },
    { run, tab: options.tab ?? 'Replay', cryptoUnavailable: options.cryptoUnavailable },
  );
  return page.locator('#results-test');
}

test('results starts paused at first flag with plain labels and advanced rules closed', async ({
  page,
}) => {
  const surface = await mountResults(page);
  await expect(surface.getByRole('note')).toHaveText(
    'Example run — no real video and no models were involved.',
  );
  await expect(surface.getByRole('slider', { name: 'Replay position' })).toHaveValue('17');
  await expect(surface.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  await expect(surface.getByRole('region', { name: 'Why this was flagged' })).toContainText(
    'It also stayed active longer than allowed first.',
  );
  await expect(surface.locator('.why-flagged strong')).toHaveText('Step skipped');
  await surface.getByRole('button', { name: 'Seek to Step skipped', exact: true }).click();
  await expect(surface.locator('.why-flagged strong')).toHaveText('Step skipped');
  await expect(surface.locator('.why-flagged strong')).toHaveAttribute(
    'aria-description',
    'skipped',
  );
  await expect(surface.locator('.ledger code').filter({ hasText: /^skipped$/ })).toHaveText(
    'skipped',
  );
  await expect(surface.locator('.ledger')).not.toHaveAttribute('open');
  await expect(surface.locator('.predicate-detail')).not.toHaveAttribute('open');
  await surface.locator('.predicate-detail summary').click();
  await expect(surface.locator('.predicate-detail pre')).toContainText('touching');
  await expect(surface.locator('.ledger')).not.toHaveAttribute('open');
  await surface.locator('.ledger > summary').click();
  await expect(surface.getByRole('columnheader', { name: 'What was seen' })).toBeVisible();
  await expect(
    surface
      .locator('.ledger .tier')
      .filter({ hasText: /^Rules engine$/ })
      .first(),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
});

test('integrity automatically verifies the report and keeps manual checks under advanced', async ({
  page,
}) => {
  const surface = await mountResults(page, { tab: 'Integrity' });
  await expect(surface.getByRole('status')).toHaveText('Report unchanged since it was created ✓');
  await expect(
    surface.getByText(
      'A local report can be rewritten together with its root. Keep the root somewhere separate.',
    ),
  ).toBeVisible();
  await expect(surface.getByRole('link', { name: 'Download report (HTML)' })).toBeVisible();
  await expect(surface.getByRole('button', { name: 'Copy root' })).toBeVisible();
  await expect(surface.getByLabel('Expected root hash')).not.toBeVisible();
  await surface.locator('.integrity-advanced > summary').click();
  await surface.getByLabel('Expected root hash').fill('0'.repeat(64));
  await surface.getByRole('button', { name: 'Verify chain', exact: true }).click();
  await expect(
    surface.getByRole('status').filter({ hasText: 'Verification failed' }),
  ).toBeVisible();
  await expect(surface.getByRole('status').filter({ hasText: 'Report unchanged' })).toBeVisible();
  await expect(
    surface.getByRole('button', { name: 'Sign in to load your own chain' }),
  ).toBeVisible();
});

test('changing visible events fails report integrity even when its chain is unchanged', async ({
  page,
}) => {
  const surface = await mountResults(page, { tab: 'Integrity', changeEvent: true });
  await expect(surface.getByRole('status')).toHaveText('This report was changed ✗');
});

test('result tabs support keyboard navigation and preserve exact integrity scope', async ({
  page,
}) => {
  const surface = await mountResults(page);
  await surface.getByRole('tab', { name: 'Replay', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(surface.getByRole('tab', { name: 'Integrity', exact: true })).toBeFocused();
  await expect(surface.getByRole('status')).toHaveText('Report unchanged since it was created ✓');
  await expect(surface.locator('.integrity-summary')).toContainText(
    'does not prove that the recording is authentic',
  );
  await page.keyboard.press('Home');
  await expect(surface.getByRole('tab', { name: 'Replay', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
});

test('live model chips use recorded counts and do not turn requested reviews into opinions', async ({
  page,
}) => {
  const surface = await mountResults(page, { live: true });
  await expect(surface.getByLabel('Models used')).toContainText('Spark · 1 call');
  await expect(surface.getByLabel('Models used')).toContainText('SAM 3.1 · 4 frames sent');
  await expect(surface.getByLabel('Models used')).toContainText('Median response · 2.00 s');
  await expect(surface.getByLabel('Models used')).not.toContainText('7 second opinions');
  await expect(surface.getByRole('note')).toHaveCount(0);
});

test('selecting a completed step does not attach an unrelated alert to it', async ({ page }) => {
  const surface = await mountResults(page);
  await surface.getByRole('button', { name: 'Seek to Step skipped', exact: true }).click();
  await surface.locator('.step').filter({ hasText: 'Approach tube 1' }).click();
  await expect(surface.locator('.why-flagged')).toHaveCount(0);
  await expect(surface.locator('.predicate-detail')).toContainText('Only visible rule evidence');
});

test('a browser verification failure is unknown, not evidence of a changed report', async ({
  page,
}) => {
  const surface = await mountResults(page, { tab: 'Integrity', cryptoUnavailable: true });
  await expect(surface.getByRole('status')).toHaveText(
    'Could not check this report. Try a secure browser connection.',
  );
  await expect(surface.getByText('This report was changed ✗')).toHaveCount(0);
});

test('an open-model request without a saved shadow opinion shows calls only', async ({ page }) => {
  const surface = await mountResults(page, { live: true, openCall: true });
  await expect(surface.getByLabel('Models used')).toContainText('Open model (spark-open) · 1 call');
  await expect(surface.getByLabel('Models used')).not.toContainText('second opinions');
});

test('copy root copies the current public sample fingerprint', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const surface = await mountResults(page, { tab: 'Integrity' });
  await surface.getByRole('button', { name: 'Copy root', exact: true }).click();
  await expect(surface.getByRole('button', { name: 'Root copied', exact: true })).toBeVisible();
  const root = await page.evaluate(() => navigator.clipboard.readText());
  expect(root).toMatch(/^[a-f0-9]{64}$/);
});

test('model paragraphs are collapsed and labelled as opinions in replay history', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const surface = await mountResults(page, { advisory: true });
  await surface.getByText('Advanced: what happened', { exact: true }).click();
  const row = surface
    .locator('tr')
    .filter({ hasText: 'Model opinion only. Rules remain unchanged.' });
  await expect(row).toHaveCount(1);
  await expect(row.getByText('advisory opinion', { exact: true })).toBeVisible();
  await expect(
    row.getByText('The final shape proves all steps happened in order.'),
  ).not.toBeVisible();
  await row.getByText('Read model opinion', { exact: true }).click();
  await expect(row.getByText('The final shape proves all steps happened in order.')).toBeVisible();
  await row.getByText('Read model opinion', { exact: true }).click();
  await expect(page).toHaveTitle(/Apprentice/);
  await expect(page.locator('vite-error-overlay')).toHaveCount(0);
  expect(errors).toEqual([]);
  if (process.env.APPRENTICE_UI_CAPTURE)
    await surface.screenshot({ path: `/tmp/apprentice-opinions-${testInfo.project.name}.png` });
});
