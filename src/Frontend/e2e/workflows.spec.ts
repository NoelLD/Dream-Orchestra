import { expect, test, type Page } from '@playwright/test'

// Läuft im Testmodus (frontend-dev) und gegen den Produktions-Build mit echtem Backend.
const shot = (name: string) => ({ path: `e2e/screenshots/${name}.png` })
// Kürzel dieses Testlaufs: nur Workflows mit diesem Kürzel werden am Ende wieder gelöscht.
const TOKEN = `e2e-${Date.now().toString(36)}`
const unique = (base: string) => `${base} ${TOKEN}`

// Gegen das echte Backend landen gespeicherte Workflows in der SQLite-Datei – danach aufräumen.
// Im Testmodus liegen sie nur im Browser; dort findet das Backend nichts mit diesem Kürzel.
test.afterEach(async ({ request }) => {
  const response = await request.get('/api/workflows').catch(() => null)
  if (!response?.ok()) return
  const list = (await response.json()) as { id: number; name: string }[]
  for (const wf of list.filter((w) => w.name.includes(TOKEN))) await request.delete(`/api/workflows/${wf.id}`)
})

async function saveAs(page: Page, name: string) {
  await page.getByLabel('Name des Workflows').fill(name)
  await page.getByRole('button', { name: 'Speichern', exact: true }).click()
  await expect(page.getByTestId('save-state')).toHaveText('gespeichert')
}

test('mehrere Workflows anlegen, öffnen, Änderungen erkennen und löschen', async ({ page }) => {
  page.on('dialog', (dialog) => void dialog.accept()) // „Ungespeicherte Änderungen verwerfen?“
  await page.goto('/')
  const first = unique('Pick-and-Place')
  const second = unique('Nur Start-Ende')

  await expect(page.getByTestId('save-state')).toHaveText('neu · nicht gespeichert')
  await saveAs(page, first)

  await page.getByRole('button', { name: 'Neu', exact: true }).click()
  await expect(page.getByLabel('Name des Workflows')).toHaveValue('Neuer Workflow')
  await expect(page.getByTestId('block-greifen')).toHaveCount(0)
  await saveAs(page, second)

  // Änderung erkennen
  await page.getByLabel('Name des Workflows').fill(`${second} (geändert)`)
  await expect(page.getByTestId('save-state')).toHaveText('● ungespeichert')

  // Ersten Workflow öffnen (Warnung wegen ungespeicherter Änderungen)
  await page.getByRole('button', { name: 'Öffnen …' }).click()
  const dialog = page.getByRole('dialog', { name: 'Workflows' })
  await expect(dialog.getByRole('alert')).toContainText('ungespeicherte Änderungen')
  await expect(dialog.getByRole('button', { name: `${first} öffnen`, exact: true })).toBeVisible()
  await page.screenshot(shot('12-workflows-dialog'))
  await dialog.getByRole('button', { name: `${first} öffnen` }).click()
  await expect(page.getByLabel('Name des Workflows')).toHaveValue(first)
  await expect(page.getByTestId('block-greifen')).toBeVisible()
  await expect(page.getByTestId('save-state')).toHaveText('gespeichert')

  // Zweiten löschen (zweistufig)
  await page.getByRole('button', { name: 'Öffnen …' }).click()
  await dialog.getByRole('button', { name: `${second} löschen` }).click()
  await dialog.getByRole('button', { name: `${second} wirklich löschen`, exact: true }).click()
  await expect(dialog.getByRole('button', { name: `${second} öffnen`, exact: true })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: `${first} öffnen`, exact: true })).toBeVisible()
})

test('„Als Kopie“ legt einen zweiten Workflow an', async ({ page }) => {
  await page.goto('/')
  const name = unique('Original')
  await saveAs(page, name)
  await page.getByRole('button', { name: 'Als Kopie' }).click()
  await expect(page.getByLabel('Name des Workflows')).toHaveValue(`${name} (Kopie)`)
  await expect(page.getByTestId('save-state')).toHaveText('gespeichert')
  await page.getByRole('button', { name: 'Öffnen …' }).click()
  const dialog = page.getByRole('dialog', { name: 'Workflows' })
  await expect(dialog.getByRole('button', { name: `${name} (Kopie) öffnen`, exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: `${name} öffnen`, exact: true })).toBeVisible()
})
