import { defineConfig, devices } from '@playwright/test'

// Läuft im Compose-Dienst "e2e" (Playwright-Image) gegen den Dev-Server im Compose-Netz.
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://frontend-dev:5173',
    viewport: { width: 1280, height: 800 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } }],
})
