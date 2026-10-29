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
