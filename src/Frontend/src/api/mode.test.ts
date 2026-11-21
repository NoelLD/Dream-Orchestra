import { describe, expect, it } from 'vitest'
import { resolveApiMode } from './mode'

describe('API-Modus aus VITE_API_MODE', () => {
  it('nimmt "mock" nur, wenn ausdrücklich gesetzt', () => {
    expect(resolveApiMode('mock')).toBe('mock')
  })

  it('nimmt "real", wenn nichts gesetzt ist – der Mock darf nie unbemerkt aktiv sein', () => {
    expect(resolveApiMode(undefined)).toBe('real')
    expect(resolveApiMode('')).toBe('real')
  })

  it('akzeptiert Groß-/Kleinschreibung und Leerzeichen', () => {
    expect(resolveApiMode(' MOCK ')).toBe('mock')
  })

  it('wirft bei unbekannten Werten einen verständlichen Fehler', () => {
    expect(() => resolveApiMode('test')).toThrow(/VITE_API_MODE.*mock.*real/)
  })
})
