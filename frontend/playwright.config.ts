import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  workers: 2,
  reporter: 'list',
  use: {
    baseURL: process.env.TEST_BASE_URL ?? 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1505, height: 1045 } },
    },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: process.env.TEST_BASE_URL
    ? undefined
    : {
        command: 'npm run dev -- --port 5174',
        env: {
          VITE_SUPABASE_URL: 'https://apprentice-test.supabase.co',
          VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_test_fixture',
          VITE_STATIC_REPLAY: 'true',
          VITE_API_BASE_URL: '',
        },
        url: 'http://127.0.0.1:5174',
        reuseExistingServer: !process.env.CI,
      },
});
