import { expect, test } from '@playwright/test'

// Nur gegen den Produktions-Container: E2E_BASE_URL=http://frontend docker compose ... run --rm e2e
test.skip(!process.env.E2E_BASE_URL?.startsWith('http://frontend/') && process.env.E2E_BASE_URL !== 'http://frontend', 'nur gegen den Produktions-Build')

test('Produktions-Build: echte API, kein Mock-Banner, Backend-Fehler werden angezeigt', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('api-mode')).toHaveText('API: echt')
  await expect(page.getByTestId('mock-banner')).toHaveCount(0)

  // Das Backend hat noch keine Fach-Endpunkte: die Oberfläche muss das verständlich zeigen statt abzustürzen (N4).
  await expect(page.getByText('Geräte nicht erreichbar')).toBeVisible()
  await page.screenshot({ path: 'e2e/screenshots/09-prod-echte-api.png' })

  const health = await page.request.get('/api/health')
  expect(health.ok()).toBe(true)
  expect(await health.json()).toEqual({ status: 'ok', service: 'backend' })
})
