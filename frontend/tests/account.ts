import type { Page } from '@playwright/test';
export const user = {
  id: '44444444-4444-4444-8444-444444444444',
  aud: 'authenticated',
  role: 'authenticated',
  email: 'ui@example.invalid',
  email_confirmed_at: '2026-10-27T00:00:00Z',
  is_anonymous: false,
  app_metadata: {},
  user_metadata: {},
  created_at: '2026-10-27T00:00:00Z',
};
export const session = {
  access_token: `${btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))}.${btoa(JSON.stringify({ sub: user.id, exp: 4102444800, role: 'authenticated' }))}.test`,
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: 4102444800,
  refresh_token: 'mock-refresh',
  user,
};
export async function mockAccount(page: Page, signedIn = true) {
  await page.route('**/auth/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({
      status: path.endsWith('/logout') ? 204 : 200,
      contentType: 'application/json',
      body: path.endsWith('/logout') ? '' : JSON.stringify(path.endsWith('/user') ? user : session),
    });
  });
  if (signedIn)
    await page.addInitScript((value) => {
      for (const ref of ['apprentice-test', 'ntuuztideqsdvuiiohlh'])
        localStorage.setItem(`sb-${ref}-auth-token`, JSON.stringify(value));
    }, session);
}
