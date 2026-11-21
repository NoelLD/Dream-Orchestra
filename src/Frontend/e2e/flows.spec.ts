import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'

const shot = (name: string) => ({ path: `e2e/screenshots/${name}.png` })

test('Pick-and-Place-Lauf: Sensor, Schleife zurück und erfolgreiches Ende (F2/F5/F10)', async ({ page }) => {
  test.setTimeout(45_000)
  await page.goto('/')
  await page.getByRole('button', { name: 'Lauf starten' }).click()
  await expect(page.getByTestId('block-greifen')).toHaveAttribute('data-active', 'true')

  // Nach dem Prompt (3 s im Testmodus) wartet der Ablauf auf die Lichtschranke.
  await expect(page.getByTestId('block-sensor')).toHaveAttribute('data-active', 'true', { timeout: 10_000 })
  await page.getByRole('switch', { name: 'Lichtschranke' }).click()

  // „Weitere Objekte“ ist an → Schleife zurück zu „Greifen“.
  await expect(page.getByTestId('block-greifen')).toHaveAttribute('data-active', 'true', { timeout: 10_000 })
  await page.screenshot(shot('05-schleife'))

  await page.getByRole('switch', { name: 'Weitere Objekte' }).click()
  await expect(page.getByTestId('run-status')).toContainText('erfolgreich', { timeout: 15_000 })
  await expect(page.getByTestId('run-credits')).toContainText('Credits verbraucht: 2')
  await page.screenshot(shot('06-erfolgreich'))
})

test('Pause, Einzelschritt und Credit-Schätzung (F8/F15)', async ({ page }) => {
  test.setTimeout(30_000)
  await page.goto('/')
  await expect(page.getByTestId('credit-estimate')).toContainText('1–2 Credits/Durchlauf · Schleife')
  // Bedienelemente dürfen nicht verdeckt sein: Klicks ohne force.
  await page.getByRole('button', { name: 'Lauf starten' }).click()
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await expect(page.getByTestId('run-status')).toContainText('pausiert')
  await page.screenshot(shot('08-pausiert'))

  await page.getByRole('button', { name: 'Einzelschritt' }).click()
  // Prompt läuft 3 s zu Ende, dann Halt am nächsten Block „Objekt in Kiste?“.
  await expect(page.getByTestId('block-sensor')).toHaveAttribute('data-active', 'true', { timeout: 10_000 })
  await expect(page.getByTestId('run-status')).toContainText('pausiert')
  await page.getByRole('button', { name: 'Weiter' }).click()
  await expect(page.getByTestId('run-status')).toContainText('läuft')
  await page.getByTestId('stop-button').click()
  await expect(page.getByTestId('run-status')).toContainText('gestoppt')
})

test('Export und Import über die Oberfläche (F3)', async ({ page }, testInfo) => {
  await page.goto('/')
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Exportieren' }).click()
  const download = await downloadPromise
  const exportedPath = testInfo.outputPath('export.json')
  await download.saveAs(exportedPath)
  const exported = JSON.parse(await readFile(exportedPath, 'utf8')) as { name: string; nodes: unknown[] }
  expect(exported.name).toBe('Pick-and-Place (Demo)')
  expect(exported.nodes).toHaveLength(7)

  await page.getByTestId('import-input').setInputFiles({
    name: 'umbenannt.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ ...exported, name: 'Importierter Ablauf' })),
  })
  await expect(page.getByLabel('Name des Workflows')).toHaveValue('Importierter Ablauf')

  await page.getByTestId('import-input').setInputFiles({ name: 'kaputt.json', mimeType: 'application/json', buffer: Buffer.from('{ nein') })
  await expect(page.getByText('Import fehlgeschlagen')).toBeVisible()
})

test('Skill anlegen und doppelten Namen ablehnen', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Skills' }).click()
  await page.getByRole('button', { name: 'Neuer Skill' }).click()
  await page.getByLabel('Name').fill('Greifen')
  await page.getByLabel('Beschreibung').fill('Greift ein Werkstück vom Band')
  await page.getByRole('button', { name: 'Speichern' }).click()
  await expect(page.getByRole('cell', { name: 'Greifen', exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Neuer Skill' }).click()
  await page.getByLabel('Name').fill('Greifen')
  await page.getByRole('button', { name: 'Speichern' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'existiert bereits' })).toBeVisible()
  await page.screenshot(shot('07-skills'))
})
