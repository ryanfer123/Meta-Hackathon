import { test, expect } from '@playwright/test';

test('known errors have plain wording while preserving their original detail', async ({ page }) => {
  await page.goto('/');
  const checks = await page.evaluate(async () => {
    const { friendlyError } = await import('/src/api.ts');
    return [
      'SAM per-run call cap reached (3000)',
      'Cannot decode recording',
      'JWT expired',
      'Ambiguous objects',
    ].map((raw) => ({ raw, ...friendlyError(new Error(raw)) }));
  });
  expect(checks[0].message).toContain('spending limit');
  expect(checks[1].message).toContain('video could not be read');
  expect(checks[2].message).toContain('fresh sign-in');
  expect(checks[3].message).toContain('identified clearly');
  for (const check of checks) expect(check.details).toBe(check.raw);
});

test('plain backend error objects retain their message and friendly explanation', async ({
  page,
}) => {
  await page.goto('/');
  const mapped = await page.evaluate(async () => {
    const { friendlyError } = await import('/src/api.ts');
    return friendlyError({ message: 'run cost reservation cap reached', code: 'test' });
  });
  expect(mapped.message).toContain('spending limit');
  expect(mapped.details).toBe('run cost reservation cap reached');
});

test('model response limits are distinct from spending and sign-in limits', async ({ page }) => {
  await page.goto('/');
  const mapped = await page.evaluate(async () => {
    const { friendlyError } = await import('/src/api.ts');
    return [
      'Model output was incomplete or exhausted its token budget',
      'run cost reservation cap reached',
      'JWT token expired',
    ].map((raw) => ({ raw, ...friendlyError(new Error(raw)) }));
  });
  expect(mapped[0].message).toContain('did not finish its response');
  expect(mapped[0].message).not.toContain('spending');
  expect(mapped[1].message).toContain('spending limit');
  expect(mapped[2].message).toContain('fresh sign-in');
  for (const result of mapped) expect(result.details).toBe(result.raw);
});
