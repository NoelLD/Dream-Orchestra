import type { ApiMode } from './contract'

/** Nicht gesetzt => "real". Der Mock muss ausdrücklich gewählt werden (N2). */
export function resolveApiMode(raw: string | undefined): ApiMode {
  const value = (raw ?? '').trim().toLowerCase()
  if (value === '' || value === 'real') return 'real'
  if (value === 'mock') return 'mock'
  throw new Error(`Ungültiger Wert für VITE_API_MODE: „${raw}“. Erlaubt sind „mock“ oder „real“.`)
}
