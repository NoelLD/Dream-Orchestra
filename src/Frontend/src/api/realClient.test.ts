import { describe, expect, it } from 'vitest'
import { ApiError, createRealClient } from './realClient'

type Call = { url: string; init: RequestInit | undefined }

function fakeFetch(respond: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = []
  const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
    const call = { url: String(input), init }
    calls.push(call)
    return respond(call)
  }
  return { fn: fn as typeof fetch, calls }
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const run = {
  id: 'r1',
  workflowId: null,
  status: 'running',
  activeNodeId: 'n2',
  startedAt: '2026-11-21T10:00:00Z',
  finishedAt: null,
  error: null,
  credits: { used: 1 },
  log: [],
}

describe('realer API-Client', () => {
  it('meldet den Modus "real"', () => {
    expect(createRealClient(fakeFetch(() => json({})).fn).mode).toBe('real')
  })

  it('holt einen Lauf über GET /api/runs/{id} und gibt ihn geprüft zurück', async () => {
    const f = fakeFetch(() => json(run))
    const result = await createRealClient(f.fn).getRun('r1')
    expect(f.calls[0]?.url).toBe('/api/runs/r1')
    expect(f.calls[0]?.init?.method ?? 'GET').toBe('GET')
    expect(result.activeNodeId).toBe('n2')
  })

  it('schickt Gerätewerte als PUT mit JSON-Body', async () => {
    const f = fakeFetch(() => json({ id: 'taster', name: 'Taster', kind: 'sensor', type: 'button', adapter: 'virtual', value: true }))
    await createRealClient(f.fn).setDevice('taster', true)
    expect(f.calls[0]?.url).toBe('/api/devices/taster')
    expect(f.calls[0]?.init?.method).toBe('PUT')
    expect(JSON.parse(String(f.calls[0]?.init?.body))).toEqual({ value: true })
  })

  it('lehnt Antworten ab, die nicht dem Vertrag entsprechen', async () => {
    const f = fakeFetch(() => json({ id: 'r1', status: 'kaputt' }))
    await expect(createRealClient(f.fn).getRun('r1')).rejects.toThrow(/entspricht nicht dem API-Vertrag/)
  })

  it('übernimmt die Fehlermeldung des Backends samt HTTP-Status', async () => {
    const f = fakeFetch(() => json({ error: 'Workflow nicht gefunden' }, 404))
    const error = await createRealClient(f.fn).getWorkflow('x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(404)
    expect((error as ApiError).message).toContain('Workflow nicht gefunden')
  })

  it('meldet ein nicht erreichbares Backend verständlich', async () => {
    const f = fakeFetch(() => {
      throw new TypeError('fetch failed')
    })
    await expect(createRealClient(f.fn).health()).rejects.toThrow(/Backend nicht erreichbar/)
  })
})
