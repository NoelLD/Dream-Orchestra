import { describe, expect, it } from 'vitest'
import { createMockClient } from './mockClient'
import { createRealClient } from './realClient'

type Call = { url: string; init: RequestInit | undefined }

function fakeFetch(respond: (call: Call) => Response) {
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

const session = {
  cell: 'cnc',
  status: 'running',
  sim_seconds: 12.5,
  busy: null,
  sensors: { door_open: true, stack_light: 'green', cycles: 1 },
  events: [{ t: 1.2, text: 'Aktion: door_open' }],
}

const results = {
  generated_at: '2026-11-22T10:37:00',
  base: 'beta-main',
  tasks: ['cnc_load'],
  task_names: { cnc_load: 'Load CNC' },
  models: [
    {
      label: 'beta-main', name: 'Base', what: 'no fine-tune', prereg: true, k: 6, lo: 0.07, hi: 0.29, contact: 8,
      buckets: { success: 6, no_grasp: 34 }, tasks: { cnc_load: 3 }, scenes: [['success', false, 'success']],
    },
    {
      label: 'ft-main', name: 'Fine-tune', what: 'c500', prereg: true, k: 14, lo: 0.22, hi: 0.5, contact: 17,
      buckets: { success: 14 }, tasks: { cnc_load: 7 }, scenes: [['no_grasp', true, 'timeout_no_grasp']],
      win: 11, loss: 3, p: 0.057,
    },
  ],
  spend: { jobs: [{ name: 'yam-cells-c500', status: 'succeeded', usd: 100 }], evals: { 'ft-main': 1.8 }, credit: 1000 },
  queue: [{ label: 'beta-main2', name: 'Base, second run', eta: '~11:25', done: false }],
  public_url: 'https://example.invalid',
}

describe('Zellen-Leitstand über den echten Client', () => {
  it('startet eine Sitzung, liest sie und schickt Aktion und Task an /api/cells', async () => {
    const { fn, calls } = fakeFetch((c) => (c.url.endsWith('/session') && c.init?.method === 'GET' ? json(session) : json({ queued: 'x' }, 202)))
    const api = createRealClient(fn)
    await api.startCellSession('cnc')
    expect((await api.getCellSession())?.sensors).toEqual(session.sensors)
    await api.cellAction('door_open')
    await api.cellTask('cnc_load', 1000)
    expect(calls.map((c) => `${c.init?.method} ${c.url}`)).toEqual([
      'POST /api/cells/cnc/session',
      'GET /api/cells/session',
      'POST /api/cells/session/action',
      'POST /api/cells/session/task',
    ])
    expect(JSON.parse(String(calls[3]?.init?.body))).toEqual({ task: 'cnc_load', seed: 1000 })
  })

  it('liefert null, wenn keine Sitzung läuft (409 no_session)', async () => {
    const api = createRealClient(fakeFetch(() => json({ error: 'no_session', detail: 'no cell session' }, 409)).fn)
    expect(await api.getCellSession()).toBeNull()
  })

  it('baut die Bild-URL mit Ansicht und Zähler gegen den Browser-Cache', () => {
    const api = createRealClient(fakeFetch(() => json({})).fn)
    expect(api.cellFrameUrl('robot', 7)).toBe('/api/cells/session/frame.jpg?view=robot&t=7')
  })

  it('liest die Fine-Tune-Ergebnisse und prüft sie gegen den Vertrag', async () => {
    const api = createRealClient(fakeFetch(() => json(results)).fn)
    const data = await api.getCellResults()
    expect(data.models[1]?.p).toBe(0.057)
    const broken = createRealClient(fakeFetch(() => json({ ...results, models: 'x' })).fn)
    await expect(broken.getCellResults()).rejects.toThrow(/API-Vertrag/)
  })
})

describe('Zellen-Leitstand im Testmodus', () => {
  it('spielt eine Sitzung nach: Aktion schaltet Sensor, Task endet nach Ablauf mit Ergebnis', async () => {
    let now = 0
    const api = createMockClient({ now: () => now })
    expect(await api.getCellSession()).toBeNull()
    await api.startCellSession('cnc')
    await api.cellAction('door_open')
    expect((await api.getCellSession())?.sensors?.door_open).toBe(true)
    await api.cellTask('cnc_load')
    expect((await api.getCellSession())?.busy).toBe('cnc_load')
    now = 10_000
    const done = await api.getCellSession()
    expect(done?.busy).toBeNull()
    expect(done?.last_result?.passed).toBe(true)
    await expect(api.cellTask('sort_round')).rejects.toThrow(/Zelle/)
  })

  it('kennzeichnet Bild und Ergebnisse als Testdaten', async () => {
    const api = createMockClient()
    expect(api.cellFrameUrl('overview', 1)).toMatch(/^data:image\/svg\+xml/)
    expect(decodeURIComponent(api.cellFrameUrl('overview', 1))).toContain('TESTMODUS')
    expect((await api.getCellResults()).models.length).toBeGreaterThan(1)
    expect((await api.listRobots())[0]?.name).toBe('yam-sim')
  })
})
