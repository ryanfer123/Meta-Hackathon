import { test, expect } from '@playwright/test';
import type { Run } from '../src/types';

const expected = [
  ['skipped-cap', 'skipped', 17, 'cap'],
  ['wrong-tube', 'wrong_object', 5, 'approach'],
  ['slow-action', 'dwell_exceeded', 7.5, 'approach'],
  ['swapped-order', 'skipped', 13, 'cap'],
  ['occlusion', 'uncertain', 12.5, 'cap'],
  ['clean', null, null, null],
] as const;

for (const [name, kind, t, step_id] of expected) {
  test(`headline helper selects ${name} without changing events`, async ({ page }) => {
    await page.goto('/');
    const run: Run = await page.request.get(`/samples/${name}.json`).then((r) => r.json());
    const result = await page.evaluate(async (run) => {
      const load = new Function('return import("/src/lib/alerts.ts")');
      const { headlineAlert } = await load();
      const before = JSON.stringify(run);
      const event = headlineAlert(run);
      return { event, unchanged: before === JSON.stringify(run) };
    }, run);
    expect(result.unchanged).toBe(true);
    if (kind) expect(result.event).toMatchObject({ kind, t, step_id });
    else expect(result.event).toBeUndefined();
    await page.goto(`/#/workspace?view=Results&tab=Replay&sample=${name}`);
    await expect(page.getByRole('slider', { name: 'Replay position' })).toHaveValue(String(t ?? 0));
    if (kind)
      await expect(page.locator('.why-flagged strong')).toHaveAttribute('aria-description', kind);
    else await expect(page.locator('.why-flagged')).toHaveCount(0);
  });
}

test('fallback uses earliest affected protocol step, severity, then time; stale focus is ignored', async ({
  page,
}) => {
  await page.goto('/');
  const run: Run = await page.request.get('/samples/skipped-cap.json').then((r) => r.json());
  const result = await page.evaluate(async (run) => {
    const load = new Function('return import("/src/lib/alerts.ts")');
    const { headlineAlert, earlierAlertContext } = await load();
    const event = run.events[0];
    run.focus = { kind: 'skipped', t: 999, step_id: 'missing' };
    run.events = [
      { ...event, kind: 'skipped', step_id: 'cap', t: 1 },
      { ...event, kind: 'dwell_exceeded', step_id: 'approach', t: 2 },
      { ...event, kind: 'wrong_object', step_id: 'approach', t: 5 },
      { ...event, kind: 'wrong_object', step_id: 'approach', t: 4 },
    ];
    const fallback = headlineAlert(run);
    const context = earlierAlertContext(run, fallback);
    run.focus = { kind: 'skipped', t: 1, step_id: 'cap' };
    const explicit = headlineAlert(run);
    const unrelated = earlierAlertContext(run, explicit);
    run.events = [{ ...event, step_id: null, kind: 'uncertain', t: 3 }];
    const unassigned = headlineAlert(run);
    run.events = [];
    return { fallback, context, explicit, unrelated, unassigned, empty: headlineAlert(run) };
  }, run);
  expect(result.fallback).toMatchObject({ kind: 'wrong_object', t: 4, step_id: 'approach' });
  expect(result.context).toBe('It also stayed active longer than allowed first.');
  expect(result.explicit).toMatchObject({ kind: 'skipped', t: 1, step_id: 'cap' });
  expect(result.unrelated).toBe('');
  expect(result.unassigned).toMatchObject({ kind: 'uncertain', t: 3, step_id: null });
  expect(result.empty).toBeUndefined();
});

test('fallback applies every severity rank and ignores non-alert focus', async ({ page }) => {
  await page.goto('/');
  const run: Run = await page.request.get('/samples/skipped-cap.json').then((r) => r.json());
  const selected = await page.evaluate(async (run) => {
    const load = new Function('return import("/src/lib/alerts.ts")');
    const { headlineAlert } = await load();
    const kinds = [
      'wrong_object',
      'skipped',
      'out_of_order',
      'dwell_too_short',
      'dwell_exceeded',
      'uncertain',
      'shadow_disagreement',
      'escalated',
    ];
    const base = run.events[0];
    run.focus = { kind: 'step_completed', t: 0, step_id: 'approach' };
    return kinds.map((_, i) => {
      run.events = [
        { ...base, kind: 'step_completed', t: 0, step_id: 'approach' },
        ...kinds
          .slice(i)
          .reverse()
          .map((kind, j) => ({ ...base, kind, t: j + 1, step_id: 'approach' })),
      ];
      return headlineAlert(run)?.kind;
    });
  }, run);
  expect(selected).toEqual([
    'wrong_object',
    'skipped',
    'out_of_order',
    'dwell_too_short',
    'dwell_exceeded',
    'uncertain',
    'shadow_disagreement',
    'escalated',
  ]);
});
