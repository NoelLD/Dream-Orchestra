import { expect, test } from '@playwright/test'

// Läuft im Testmodus (frontend-dev) und gegen den Produktions-Build mit echtem Backend.
const shot = (name: string) => ({ path: `e2e/screenshots/${name}.png` })
const TOKEN = `e2e${Date.now().toString(36)}`

// Gegen das echte Backend landen Geräte in der SQLite-Datei – danach aufräumen.
test.afterEach(async ({ request }) => {
  const response = await request.get('/api/devices').catch(() => null)
  if (!response?.ok()) return
  const list = (await response.json()) as { id: string; name: string }[]
  for (const d of list.filter((x) => x.name.includes(TOKEN))) await request.delete(`/api/devices/${d.id}`)
})

test('Gerät mit MQTT anlegen, im Workflow nutzen und in der Geräteleiste sehen', async ({ page }) => {
  page.on('dialog', (dialog) => void dialog.accept())
  const name = `Tor offen ${TOKEN}`
  await page.goto('/')

  // Beispiel-Workflow: Leiste zeigt nur dessen Geräte
  const bar = page.getByRole('region', { name: 'Geräteleiste' })
  await expect(bar.getByTestId('device-lichtschranke')).toBeVisible()
  await expect(bar.getByTestId('device-taster')).toHaveCount(0)
  await expect(bar.getByTestId('device-protocol-lichtschranke')).toHaveText('virtuell')

  // Gerät anlegen
  await page.getByRole('tab', { name: 'Geräte' }).click()
  await expect(page.getByTestId('device-row-lichtschranke')).toBeVisible()
  await page.getByRole('button', { name: 'Neues Gerät' }).click()
  const dialog = page.getByRole('dialog', { name: 'Neues Gerät' })
  await dialog.getByLabel('Name').fill(name)
  await dialog.getByLabel('Protokoll').click()
  await page.getByRole('option', { name: 'MQTT' }).click()
  await expect(dialog.getByLabel('Endpoint')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Speichern' }).click()
  await expect(dialog.getByRole('alert')).toContainText('Host fehlt')
  await dialog.getByLabel('Broker-Host').fill('broker.local')
  await dialog.getByLabel('Topic').fill('halle1/tor/offen')
  await dialog.getByLabel('Passwort (optional)').fill('geheim')
  await page.screenshot(shot('20-geraet-dialog-mqtt'))
  await dialog.getByRole('button', { name: 'Speichern' }).click()
  await expect(dialog).toHaveCount(0)
  const row = page.getByRole('row').filter({ hasText: name })
  await expect(row).toContainText('MQTT')
  await expect(row).toContainText('halle1/tor/offen')
  await page.screenshot(shot('21-geraete-ansicht'))

  // Im Workflow verwenden
  await page.getByRole('tab', { name: 'Workflow-Editor' }).click()
  await page.getByRole('button', { name: 'Neu', exact: true }).click()
  await expect(bar).toContainText('Noch keine Geräte im Workflow')
  await page.getByTestId('palette-waitSensor').click()
  await page.getByLabel('Sensor', { exact: true }).click()
  await page.getByRole('option', { name: new RegExp(name) }).click()
  const id = `tor-offen-${TOKEN}`
  await expect(bar.getByTestId(`device-${id}`)).toBeVisible()
  await expect(bar.getByTestId(`device-protocol-${id}`)).toHaveText('MQTT')
  // Sensor bedienen
  await bar.getByRole('switch', { name }).click()
  await expect(bar.getByRole('switch', { name })).toBeChecked()
  await page.screenshot(shot('22-geraeteleiste-workflow'))

  // Gespeichert verwendet -> Löschen gesperrt
  await page.getByLabel('Name des Workflows').fill(`Tor ${TOKEN}`)
  await page.getByRole('button', { name: 'Speichern', exact: true }).click()
  await expect(page.getByTestId('save-state')).toHaveText('gespeichert')
  await page.getByRole('tab', { name: 'Geräte' }).click()
  await page.getByRole('button', { name: `${name} löschen` }).click()
  await page.getByRole('dialog', { name: 'Gerät löschen?' }).getByRole('button', { name: 'Löschen' }).click()
  await expect(page.getByText(/Löschen nicht möglich/)).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: name })).toBeVisible()

  // Aufräumen für das echte Backend: Workflow löschen, dann Gerät
  const workflows = await page.request.get('/api/workflows').catch(() => null)
  if (workflows?.ok()) {
    for (const wf of (await workflows.json()) as { id: number; name: string }[]) {
      if (wf.name.includes(TOKEN)) await page.request.delete(`/api/workflows/${wf.id}`)
    }
  }
})
