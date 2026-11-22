import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/realClient'
import { shouldForgetRun } from './useRun'

describe('gemerkter Lauf nach Neuladen (Codex Review 5)', () => {
  it('wird nur bei „Lauf nicht gefunden“ verworfen, nicht bei vorübergehenden Fehlern', () => {
    expect(shouldForgetRun(new ApiError('weg', 404))).toBe(true)
    expect(shouldForgetRun(new ApiError('Backend startet', 503))).toBe(false)
    expect(shouldForgetRun(new ApiError('Netz weg', null))).toBe(false)
    expect(shouldForgetRun(new Error('unbekannt'))).toBe(false)
  })
})
