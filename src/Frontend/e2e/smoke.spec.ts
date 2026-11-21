import { expect, test } from '@playwright/test'

const shot = (name: string) => ({ path: `e2e/screenshots/${name}.png`, fullPage: false })

test.describe('DreamOrchestra Smoke-Test (Testmodus)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('zeigt das Banner „SIMULIERTE API“ und den Beispiel-Workflow', async ({ page }) => {
    await expect(page.getByTestId('mock-banner')).toContainText('SIMULIERTE API')
    await expect(page.getByTestId('stop-button')).toBeVisible()
    for (const id of ['start', 'greifen', 'sensor', 'weiter', 'ende']) {
      await expect(page.getByTestId(`block-${id}`)).toBeVisible()
    }
    // Die Rückkante (Schleife) muss sichtbar über den Blöcken verlaufen.
    await expect(page.locator('.react-flow__edge').getByText('Schleife')).toBeVisible()
    await page.screenshot(shot('01-editor'))
  })

  test('startet einen Lauf, hebt den aktiven Block hervor und stoppt ihn', async ({ page }) => {
    await page.getByRole('button', { name: 'Lauf starten' }).click()
    const active = page.getByTestId('block-greifen')
    await expect(active).toHaveAttribute('data-active', 'true')
    await expect(page.getByTestId('run-status')).toContainText('läuft')
    await page.screenshot(shot('02-lauf-aktiv'))

    await page.getByTestId('stop-button').click()
    await expect(page.getByTestId('run-status')).toContainText('gestoppt')
    await expect(active).not.toHaveAttribute('data-active', 'true')
    await page.screenshot(shot('03-gestoppt'))
  })

  test('markiert Fehler am Block, wenn die Prüfung vor dem Start scheitert', async ({ page }) => {
    await page.getByTestId('palette-prompt').click()
    await page.getByRole('button', { name: 'Lauf starten' }).click()
    await expect(page.getByText('Der Prompt ist leer.')).toBeVisible()
    await expect(page.getByText('Block ist nicht mit dem Start verbunden.')).toBeVisible()
    await expect(page.getByTestId('run-status')).toHaveCount(0)
    await page.screenshot(shot('04-pruefung-fehler'))
  })
})
