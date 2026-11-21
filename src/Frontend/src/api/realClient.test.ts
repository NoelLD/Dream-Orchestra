import { describe, expect, it } from 'vitest'
import { SAMPLE_WORKFLOW } from '@/workflow/sample'
import { ApiError, createRealClient, validationFromError } from './realClient'

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

/** Antwort des Backends (GET /api/runs/{id}) */
const run = {
  id: 1,
  workflow_id: null,
  status: 'running',
  api_mode: 'mock',
  active_block_id: 'n2',
  started_at: '2026-11-21T10:00:00Z',
  finished_at: null,
  credits_estimate: 1,
  credits_used: 1,
  error: null,
  log: [],
  cursor: 0,
}

describe('realer API-Client', () => {
  it('meldet den Modus "real"', () => {
    expect(createRealClient(fakeFetch(() => json({})).fn).mode).toBe('real')
  })

  it('holt einen Lauf über GET /api/runs/{id} und gibt ihn geprüft zurück', async () => {
    const f = fakeFetch(() => json(run))
    const result = await createRealClient(f.fn).getRun('1')
    expect(f.calls[0]?.url).toBe('/api/runs/1')
    expect(f.calls[0]?.init?.method ?? 'GET').toBe('GET')
    expect(result).toMatchObject({ id: '1', activeNodeId: 'n2', credits: { used: 1 } })
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

  it('startet eine Momentaufnahme im Backend-Format (definition + workflow_id)', async () => {
    const f = fakeFetch(() => json(run, 202))
    const result = await createRealClient(f.fn).startRun({ workflowId: '4', workflow: SAMPLE_WORKFLOW })
    expect(f.calls[0]?.url).toBe('/api/runs')
    const body = JSON.parse(String(f.calls[0]?.init?.body)) as { workflow_id: number; definition: { blocks: { type: string }[] } }
    expect(body.workflow_id).toBe(4)
    expect(body.definition.blocks.map((b) => b.type)).toContain('wait_sensor')
    expect(result.id).toBe('1')
  })

  it('speichert Workflows als {name, definition} und liefert String-IDs', async () => {
    const stored = { id: 9, name: 'Demo', created_at: 'x', updated_at: 'y', definition: { blocks: [], edges: [] } }
    const f = fakeFetch(() => json(stored, 201))
    const wf = await createRealClient(f.fn).createWorkflow({ ...SAMPLE_WORKFLOW, name: 'Demo' })
    const body = JSON.parse(String(f.calls[0]?.init?.body)) as { name: string; definition: unknown }
    expect(body.name).toBe('Demo')
    expect(body.definition).toHaveProperty('blocks')
    expect(wf.id).toBe('9')
  })

  it('übernimmt detail als Meldung und reicht das Prüfergebnis bei 422 durch', async () => {
    const details = { valid: false, errors: [{ message: 'Leerer Prompt', block_id: 'greifen' }], warnings: [], credits_estimate: 1 }
    const f = fakeFetch(() => json({ error: 'invalid', detail: 'Workflow ist nicht startbereit', details }, 422))
    const error = await createRealClient(f.fn).startRun({ workflowId: null, workflow: SAMPLE_WORKFLOW }).catch((e: unknown) => e)
    expect((error as ApiError).message).toContain('Workflow ist nicht startbereit')
    expect((error as ApiError).code).toBe('invalid')
    expect(validationFromError(error)).toEqual({
      valid: false,
      issues: [{ nodeId: 'greifen', message: 'Leerer Prompt' }],
      creditsEstimate: 1,
    })
  })
})
