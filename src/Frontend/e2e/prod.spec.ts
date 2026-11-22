import { expect, test } from '@playwright/test'

// Nur gegen den Produktions-Container (nginx -> echtes Backend, Backend im Modus mock):
// E2E_BASE_URL=http://frontend docker compose --profile e2e run --rm --no-deps e2e
test.skip(!process.env.E2E_BASE_URL?.startsWith('http://frontend/') && process.env.E2E_BASE_URL !== 'http://frontend', 'nur gegen den Produktions-Build')

const shot = (name: string) => ({ path: `e2e/screenshots/${name}.png` })

test('Produktions-Build: echtes Backend über /api, Banner zeigt dessen Modus', async ({ page }) => {
  const status = await page.request.get('/api/status')
  expect(status.ok()).toBe(true)
  const { api_mode: mode } = (await status.json()) as { api_mode: string }

  await page.goto('/')
  if (mode === 'real') {
    await expect(page.getByTestId('api-mode')).toHaveText('API: live')
    await expect(page.getByTestId('mock-banner')).toHaveCount(0)
  } else {
    await expect(page.getByTestId('api-mode')).toHaveText(mode === 'sim' ? 'API: PRECOMPUTED (sim)' : `API: SIMULATED (${mode})`)
    await expect(page.getByTestId('mock-banner')).toContainText(mode === 'sim' ? 'PRECOMPUTED' : 'SIMULATED API')
  }
  // Geräte kommen aus dem Backend
  await expect(page.getByRole('switch', { name: 'Lichtschranke' })).toBeVisible()
  await page.screenshot(shot('09-prod-echtes-backend'))

  const health = await page.request.get('/api/health')
  expect(await health.json()).toEqual({ status: 'ok', service: 'backend' })
})

test('Produktions-Build: Pick-and-Place-Lauf über das Backend (Schleife, Erfolg, Credits)', async ({ page }) => {
  test.setTimeout(60_000)
  const status = (await (await page.request.get('/api/status')).json()) as { api_mode: string }
  test.skip(status.api_mode !== 'mock', 'nur mit Backend im Modus mock (keine Simulation, keine Credits)')

  // Startzustand der virtuellen Geräte im Backend setzen
  await page.request.put('/api/devices/lichtschranke/value', { data: { value: false } })
  await page.request.put('/api/devices/weitere-objekte/value', { data: { value: true } })

  await page.goto('/')
  await page.getByRole('button', { name: 'Start run' }).click()
  await expect(page.getByTestId('block-greifen')).toHaveAttribute('data-active', 'true')
  await expect(page.getByTestId('block-sensor')).toHaveAttribute('data-active', 'true', { timeout: 15_000 })

  await page.getByRole('switch', { name: 'Lichtschranke' }).click()
  await expect(page.getByTestId('block-greifen')).toHaveAttribute('data-active', 'true', { timeout: 15_000 })
  await page.getByRole('switch', { name: 'Weitere Objekte' }).click()

  await expect(page.getByTestId('run-status')).toContainText('erfolgreich', { timeout: 20_000 })
  await expect(page.getByTestId('run-credits')).toContainText('Credits verbraucht: 2')
  await expect(page.getByText('Ende erreicht')).toBeVisible()
  await page.screenshot(shot('10-prod-lauf-erfolgreich'))
})

test('Produktions-Build: „Prüfen“ fragt nach der lokalen Prüfung auch das Backend', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByText(/Prüfung bestanden \(Backend\) · ≈ 2 Credits/)).toBeVisible()
})
