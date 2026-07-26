import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E Test Configuration
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './e2e',

  /* Run tests in files in parallel */
  fullyParallel: true,

  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,

  /* Opt out of parallel tests on CI */
  workers: process.env.CI ? 1 : undefined,

  /* Reporter to use */
  reporter: [
    ['html', { outputFolder: 'e2e-report' }],
    ['list']
  ],

  /* Shared settings for all the projects below */
  use: {
    /* Base URL to use in actions like `await page.goto('/')` */
    baseURL: 'http://localhost:5735',

    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',

    /* Screenshot on failure */
    screenshot: 'only-on-failure',

    /* Video recording */
    video: 'on-first-retry',

    /* Viewport size */
    viewport: { width: 1280, height: 720 },

    /* Browser permissions */
    permissions: ['storage-access'],

    /* Launch options */
    launchOptions: {
      args: ['--disable-web-security', '--allow-file-access-from-files']
    }
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],

  /* Run local preview server before starting the tests */
  webServer: {
    command: 'npx vite preview --port 5735',
    url: 'http://localhost:5735',
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  }
})
