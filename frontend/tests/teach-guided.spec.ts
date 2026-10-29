import { test, expect, type Page } from '@playwright/test';
import { mockAccount } from './account';

async function mountTeach(page: Page, withProcedure = false, replayMode = false) {
  await mockAccount(page);
  await page.route('**/__teach-test', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: `<!doctype html><html><head><meta name="viewport" content="width=device-width"></head><body><div id="root"></div><script type="module">
    import React from '/node_modules/.vite/deps/react.js';
    import client from '/node_modules/.vite/deps/react-dom_client.js';
    import RefreshRuntime from '/@react-refresh';
    RefreshRuntime.injectIntoGlobalHook(window);
    window.$RefreshReg$ = () => {};
    window.$RefreshSig$ = () => (type) => type;
    window.__vite_plugin_react_preamble_installed__ = true;
    const { Learn } = await import('/src/Learn.tsx');
    import '/src/styles.css';
    const run=await (await fetch('/samples/skipped-cap.json')).json();
    const initialJob=${withProcedure ? "{id:'mock-procedure',result:{protocol:run.protocol,boundary_suggestions:{approach:{start:0,end:2}}}}" : 'null'};
    client.createRoot(document.getElementById('root')).render(React.createElement(Learn,{run,health:{replay_mode:${String(replayMode)},live_configured:true,glimmer_configured:false},onRun:()=>{},initialJob,onNavigateCheck:()=>{},onProtocolReady:(value)=>{document.documentElement.dataset.procedureId=value.id}}));
  </script></body></html>`,
    }),
  );
  await page.route('**/api/media/mock-procedure/original.mp4', (route) =>
    route.fulfill({ contentType: 'video/mp4', body: 'mock-media-placeholder' }),
  );
  await page.goto('/__teach-test');
}

test('Teach starts with plain narration and explains disabled controls; sample steps are read-only', async ({
  page,
}) => {
  await mountTeach(page);
  await expect(page.getByRole('heading', { name: '1 Show the right way' })).toBeVisible();
  const create = page.getByRole('button', { name: 'Create the steps' });
  await expect(create).toBeDisabled();
  await expect(create).toHaveAccessibleDescription('Add a video to continue.');
  await expect(page.getByLabel('Describe what happens (optional)')).toHaveValue('');
  await expect(page.locator('textarea')).toHaveCount(1);
  await page.getByRole('button', { name: 'Use the sample steps' }).click();
  await expect(page.getByText('Example', { exact: true })).toBeVisible();
  await expect(page.locator('.validation-checks')).toHaveCount(0);
  await expect(page.locator('.teaching-player')).toHaveCount(0);
  await expect(page.locator('pre:visible')).toHaveCount(0);
  await page.getByText('Advanced details', { exact: true }).click();
  await expect(page.locator('pre').first()).toBeVisible();
  await expect(page.locator('pre').first()).toContainText('touching');
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
});

test('Teach seeds missing timings from actual duration and requires review after every edit', async ({
  page,
}) => {
  await mountTeach(page, true);
  await expect(page.getByRole('heading', { name: '2 Check the steps' })).toBeVisible();
  await page.locator('.teaching-player').evaluate((video) => {
    Object.defineProperty(video, 'duration', { value: 12, configurable: true });
    video.dispatchEvent(new Event('loadedmetadata'));
  });
  await expect(page.getByLabel('Approach tube 1 start in seconds')).toHaveValue('0');
  await expect(page.getByLabel('Approach tube 1 end in seconds')).toHaveValue('2');
  await expect(page.getByLabel('Return the dropper start in seconds')).toHaveValue('3');
  await expect(page.getByLabel('Return the dropper end in seconds')).toHaveValue('6');
  await page
    .getByLabel('Second video (same procedure, different take)', { exact: true })
    .setInputFiles({
      name: 'second.mp4',
      mimeType: 'video/mp4',
      buffer: Buffer.from('mock-video'),
    });
  const confirm = page.getByRole('checkbox', {
    name: 'I checked every start and end against the teaching video',
  });
  await confirm.check();
  await expect(page.getByRole('button', { name: 'Run the checks' })).toBeEnabled();
  await page.getByLabel('Approach tube 1 end in seconds').fill('13');
  await expect(confirm).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Run the checks' })).toHaveAccessibleDescription(
    'Adjust the start and end for “Approach tube 1”.',
  );
  await expect(page.getByRole('button', { name: 'Run the checks' })).toBeDisabled();
  await page.getByLabel('Approach tube 1 end in seconds').fill('2');
  await page.locator('.teaching-player').evaluate((video) => {
    Object.defineProperty(video, 'currentTime', { value: 1.5, writable: true });
  });
  await page.getByRole('button', { name: 'Approach tube 1: mark start here' }).click();
  await expect(page.getByLabel('Approach tube 1 start in seconds')).toHaveValue('1.5');
  await expect(confirm).not.toBeChecked();
  await expect(page.locator('textarea')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBeFalsy();
});

test('replay mode keeps create and validation disabled even when the model key is configured', async ({
  page,
}) => {
  await mountTeach(page, true, true);
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click();
  await page
    .getByLabel('Teaching video', { exact: true })
    .setInputFiles({ name: 'new.mp4', mimeType: 'video/mp4', buffer: Buffer.from('mock-video') });
  await expect(page.getByRole('button', { name: 'Create the steps' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Create the steps' })).toHaveAccessibleDescription(
    "Analysis isn't connected here — try the sample.",
  );
});

test('changing the teaching video clears the old procedure and validation controls', async ({
  page,
}) => {
  await mountTeach(page, true);
  await expect(page.locator('html')).toHaveAttribute('data-procedure-id', 'mock-procedure');
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click();
  await page
    .getByLabel('Teaching video', { exact: true })
    .setInputFiles({
      name: 'replacement.mp4',
      mimeType: 'video/mp4',
      buffer: Buffer.from('mock-video'),
    });
  await expect(page.locator('html')).toHaveAttribute('data-procedure-id', '');
  await expect(page.getByRole('button', { name: 'Run the checks' })).toHaveCount(0);
  await expect(
    page.getByLabel('Second video (same procedure, different take)', { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Create the steps' })).toBeEnabled();
});

test('changing the teaching description also requires creating the steps again', async ({
  page,
}) => {
  await mountTeach(page, true);
  await expect(page.locator('html')).toHaveAttribute('data-procedure-id', 'mock-procedure');
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click();
  await page.getByLabel('Describe what happens (optional)').fill('A new description of the task');
  await expect(page.locator('html')).toHaveAttribute('data-procedure-id', '');
  await expect(page.getByRole('button', { name: 'Run the checks' })).toHaveCount(0);
  await expect(page.locator('.step-timeline')).toHaveCount(0);
});
