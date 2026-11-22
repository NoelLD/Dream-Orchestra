import { beforeEach, describe, expect, it } from 'vitest'
import type { ApiClient, WorkflowDocument } from './contract'
import { createMockClient } from './mockClient'

let now = 0
let api: ApiClient

beforeEach(() => {
  now = 0
  api = createMockClient({ now: () => now, promptDurationMs: 3000 })
})

const doc = (nodes: WorkflowDocument['nodes'], edges: WorkflowDocument['edges']): WorkflowDocument => ({
  schemaVersion: 1,
  name: 'Test',
  nodes,
  edges,
})

const P = { x: 0, y: 0 }
const promptNode = (id: string, prompt = 'Greife', extra: Partial<{ timeoutS: number; retries: number }> = {}) =>
  ({ id, type: 'prompt', position: P, data: { prompt, skillId: null, timeoutS: 60, retries: 0, ...extra } }) as const

const linear = doc(
  [
    { id: 's', type: 'start', position: P, data: {} },
    promptNode('p'),
    { id: 'e', type: 'end', position: P, data: {} },
  ],
  [
    { id: 'e1', source: 's', target: 'p', sourceHandle: 'out' },
    { id: 'e2', source: 'p', target: 'e', sourceHandle: 'out' },
  ],
)

describe('Mock-Client (Testmodus N2)', () => {
  it('meldet den Modus "mock"', () => {
    expect(api.mode).toBe('mock')
  })

  it('führt einen Prompt-Block aus und beendet den Lauf danach erfolgreich', async () => {
    const started = await api.startRun({ workflowId: null, workflow: linear })
    expect(started.status).toBe('running')
    expect(started.activeNodeId).toBe('p')

    now = 2999
    expect((await api.getRun(started.id)).activeNodeId).toBe('p')

    now = 3000
    const done = await api.getRun(started.id)
    expect(done.status).toBe('succeeded')
    expect(done.activeNodeId).toBeNull()
    expect(done.finishedAt).not.toBeNull()
    expect(done.credits.used).toBe(1)
    const promptLog = done.log.find((entry) => entry.nodeId === 'p' && entry.apiStatus === 'succeeded')
    expect(promptLog?.durationMs).toBe(3000)
  })

  it('wartet auf einen Sensor, bis der Nutzer ihn umschaltet', async () => {
    const workflow = doc(
      [
        { id: 's', type: 'start', position: P, data: {} },
        { id: 'w', type: 'waitSensor', position: P, data: { deviceId: 'lichtschranke', operator: 'eq', value: true, timeoutS: null } },
        { id: 'e', type: 'end', position: P, data: {} },
      ],
      [
        { id: 'e1', source: 's', target: 'w', sourceHandle: 'out' },
        { id: 'e2', source: 'w', target: 'e', sourceHandle: 'out' },
      ],
    )
    const run = await api.startRun({ workflowId: null, workflow })
    now = 60_000
    expect((await api.getRun(run.id)).activeNodeId).toBe('w')

    await api.setDevice('lichtschranke', true)
    expect((await api.getRun(run.id)).status).toBe('succeeded')
  })

  it('folgt bei einer Bedingung dem Ausgang "sonst", wenn sie nicht zutrifft', async () => {
    const workflow = doc(
      [
        { id: 's', type: 'start', position: P, data: {} },
        { id: 'c', type: 'condition', position: P, data: { deviceId: 'lichtschranke', operator: 'eq', value: true } },
        promptNode('ja'),
        { id: 'e', type: 'end', position: P, data: {} },
      ],
      [
        { id: 'e1', source: 's', target: 'c', sourceHandle: 'out' },
        { id: 'e2', source: 'c', target: 'ja', sourceHandle: 'true' },
        { id: 'e3', source: 'c', target: 'e', sourceHandle: 'false' },
      ],
    )
    const run = await api.startRun({ workflowId: null, workflow })
    expect(run.status).toBe('succeeded')
    expect(run.credits.used).toBe(0)
  })

  it('schaltet Aktoren über den Block "Aktor setzen"', async () => {
    const workflow = doc(
      [
        { id: 's', type: 'start', position: P, data: {} },
        { id: 'a', type: 'setActuator', position: P, data: { deviceId: 'lampe', value: true } },
        { id: 'e', type: 'end', position: P, data: {} },
      ],
      [
        { id: 'e1', source: 's', target: 'a', sourceHandle: 'out' },
        { id: 'e2', source: 'a', target: 'e', sourceHandle: 'out' },
      ],
    )
    await api.startRun({ workflowId: null, workflow })
    const lampe = (await api.listDevices()).find((d) => d.id === 'lampe')
    expect(lampe?.value).toBe(true)
  })

  it('nimmt nach einer Zeitüberschreitung und allen Wiederholungen den Fehlerpfad', async () => {
    api = createMockClient({ now: () => now, promptDurationMs: 10_000 })
    const workflow = doc(
      [
        { id: 's', type: 'start', position: P, data: {} },
        promptNode('p', 'Greife', { timeoutS: 5, retries: 1 }),
        { id: 'ok', type: 'end', position: P, data: {} },
        { id: 'fehler', type: 'setActuator', position: P, data: { deviceId: 'lampe', value: true } },
      ],
      [
        { id: 'e1', source: 's', target: 'p', sourceHandle: 'out' },
        { id: 'e2', source: 'p', target: 'ok', sourceHandle: 'out' },
        { id: 'e3', source: 'p', target: 'fehler', sourceHandle: 'error' },
      ],
    )
    const run = await api.startRun({ workflowId: null, workflow })
    now = 5_000
    const afterFirst = await api.getRun(run.id)
    expect(afterFirst.activeNodeId).toBe('p')
    expect(afterFirst.log.some((entry) => entry.apiStatus === 'timeout')).toBe(true)

    now = 10_000
    const final = await api.getRun(run.id)
    expect(final.credits.used).toBe(2)
    expect((await api.listDevices()).find((d) => d.id === 'lampe')?.value).toBe(true)
  })

  it('beendet einen Lauf mit Fehler, wenn ein Block keinen passenden Ausgang hat', async () => {
    const workflow = doc([{ id: 's', type: 'start', position: P, data: {} }], [])
    const run = await api.startRun({ workflowId: null, workflow })
    expect(run.status).toBe('failed')
    expect(run.error).toMatch(/keinen Ausgang/)
  })

  it('stoppt einen laufenden Ablauf (F7)', async () => {
    const run = await api.startRun({ workflowId: null, workflow: linear })
    const stopped = await api.stopRun(run.id)
    expect(stopped.status).toBe('stopped')
    expect(stopped.activeNodeId).toBeNull()
    now = 10_000
    expect((await api.getRun(run.id)).status).toBe('stopped')
  })

  it('hält die Zeit an, solange ein Lauf pausiert ist, und setzt danach fort (F8)', async () => {
    const run = await api.startRun({ workflowId: null, workflow: linear })
    now = 1000
    expect((await api.pauseRun(run.id)).status).toBe('paused')

    now = 60_000
    const paused = await api.getRun(run.id)
    expect(paused.status).toBe('paused')
    expect(paused.activeNodeId).toBe('p')

    expect((await api.resumeRun(run.id)).status).toBe('running')
    now = 61_999
    expect((await api.getRun(run.id)).activeNodeId).toBe('p')
    now = 62_000
    expect((await api.getRun(run.id)).status).toBe('succeeded')
  })

  it('führt im Einzelschritt den aktuellen Block zu Ende und hält am nächsten an (F8)', async () => {
    const twoPrompts = doc(
      [{ id: 's', type: 'start', position: P, data: {} }, promptNode('p1'), promptNode('p2'), { id: 'e', type: 'end', position: P, data: {} }],
      [
        { id: '1', source: 's', target: 'p1', sourceHandle: 'out' },
        { id: '2', source: 'p1', target: 'p2', sourceHandle: 'out' },
        { id: '3', source: 'p2', target: 'e', sourceHandle: 'out' },
      ],
    )
    const run = await api.startRun({ workflowId: null, workflow: twoPrompts })
    await api.pauseRun(run.id)
    await api.stepRun(run.id)
    now = 3000
    const afterStep = await api.getRun(run.id)
    expect(afterStep.activeNodeId).toBe('p2')
    expect(afterStep.status).toBe('paused')
  })

  it('lehnt Pause für einen beendeten Lauf ab', async () => {
    const run = await api.startRun({ workflowId: null, workflow: linear })
    await api.stopRun(run.id)
    await expect(api.pauseRun(run.id)).rejects.toThrow(/nicht pausiert werden/)
  })

  it('verwaltet Skills im Speicher mit den Feldern aus schema.sql', async () => {
    const created = await api.createSkill({ name: 'Greifen', description: 'Greift ein Werkstück' })
    expect(created).toMatchObject({ name: 'Greifen', status: 'Entwurf', fine_tuned_model: null })
    const updated = await api.updateSkill(created.id, { name: 'Greifen', description: 'neu', status: 'Bereit' })
    expect(updated.status).toBe('Bereit')
    expect((await api.listSkills()).map((s) => s.name)).toContain('Greifen')
  })

  it('lehnt doppelte Skill-Namen ab (UNIQUE in schema.sql)', async () => {
    await api.createSkill({ name: 'Doppelt', description: '' })
    await expect(api.createSkill({ name: 'Doppelt', description: '' })).rejects.toThrow(/existiert bereits/)
  })
})

describe('Mock-Client: mehrere Workflows', () => {
  it('listet zuletzt geänderte zuerst und löscht Workflows', async () => {
    const a = await api.createWorkflow({ ...linear, name: 'A' })
    now = 1000
    const b = await api.createWorkflow({ ...linear, name: 'B' })
    now = 2000
    await api.updateWorkflow(a.id, { ...linear, name: 'A2' })
    expect((await api.listWorkflows()).map((w) => w.name)).toEqual(['A2', 'B'])

    await api.deleteWorkflow(b.id)
    expect((await api.listWorkflows()).map((w) => w.name)).toEqual(['A2'])
    await expect(api.getWorkflow(b.id)).rejects.toThrow(/nicht gefunden/)
    await expect(api.deleteWorkflow(b.id)).rejects.toThrow(/nicht gefunden/)
  })
})

describe('Mock-Client: Geräte verwalten', () => {
  const mqtt = { protocol: 'mqtt', host: 'b', topic: 't', port: 1883, qos: 0, tls: false, password: 'p' } as const

  it('legt Geräte mit ID aus dem Namen an und gibt kein Passwort zurück', async () => {
    const band = await api.createDevice({ name: 'Band', type: 'conveyor', config: mqtt })
    expect(band).toMatchObject({ id: 'band', kind: 'actuator', protocol: 'mqtt', simulated: true, value: false })
    expect(band.config).not.toHaveProperty('password')
    expect(band.config).toMatchObject({ password_set: true })
    expect((await api.createDevice({ name: 'Band', type: 'conveyor', config: mqtt })).id).toBe('band-2')
    expect((await api.listDevices()).map((d) => d.id)).toContain('band-2')
  })

  it('setzt beim Typwechsel den Wert zurück und behält leeres Passwort', async () => {
    await api.createDevice({ name: 'Band', type: 'conveyor', config: mqtt })
    const updated = await api.updateDevice('band', { name: 'Band', type: 'conveyor', config: { ...mqtt, password: null } })
    expect(updated.config).toMatchObject({ password_set: true })
    await api.setDevice('fuellstand', 4)
    const sw = await api.updateDevice('fuellstand', { name: 'Füllstand', type: 'switch', config: { protocol: 'virtual' } })
    expect(sw).toMatchObject({ id: 'fuellstand', value: false, kind: 'sensor' })
  })

  it('blockiert das Löschen, solange ein gespeicherter Workflow das Gerät nutzt', async () => {
    await api.createWorkflow(
      doc(
        [
          { id: 's', type: 'start', position: P, data: {} },
          { id: 'a', type: 'setActuator', position: P, data: { deviceId: 'lampe', value: true } },
        ],
        [],
      ),
    )
    const error = await api.deleteDevice('lampe').catch((e: unknown) => e)
    expect(error).toMatchObject({ status: 409 })
    expect((error as Error).message).toContain('Test')
    await api.deleteDevice('taster')
    expect((await api.listDevices()).map((d) => d.id)).not.toContain('taster')
  })
})
