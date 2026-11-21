import { describe, expect, it } from 'vitest'
import { SAMPLE_WORKFLOW } from '@/workflow/sample'
import {
  BackendRunSchema,
  fromBackendDefinition,
  fromBackendRun,
  fromBackendWorkflow,
  toBackendDefinition,
  toBackendWorkflowId,
} from './backendMapping'

describe('toBackendDefinition', () => {
  it('übersetzt Blocktypen, Parameter, Operatoren und Ausgänge', () => {
    const def = toBackendDefinition(SAMPLE_WORKFLOW)
    const byId = Object.fromEntries(def.blocks.map((b) => [b.id, b]))

    expect(byId.greifen).toEqual({
      id: 'greifen',
      type: 'prompt',
      position: { x: 180, y: 0 },
      params: {
        label: 'Greifen',
        prompt: 'Greife das Werkstück und lege es in die Kiste',
        skill_id: null,
        timeout_s: 60,
        retries: 1,
      },
    })
    expect(byId.sensor?.type).toBe('wait_sensor')
    expect(byId.sensor?.params).toMatchObject({ device: 'lichtschranke', operator: '==', value: true, timeout_s: 30 })
    expect(byId.stoerung?.type).toBe('set_actuator')
    expect(byId.weiter?.params).toMatchObject({ device: 'weitere-objekte', operator: '==' })

    const ports = Object.fromEntries(def.edges.map((e) => [e.id, e.port]))
    expect(ports['e-start-greifen']).toBe('next')
    expect(ports['e-greifen-stoerung']).toBe('error')
    expect(ports['e-weiter-greifen']).toBe('true')
    expect(ports['e-weiter-ende']).toBe('false')
  })

  it('übersetzt alle Vergleichsoperatoren', () => {
    const ops = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'] as const
    const def = toBackendDefinition({
      nodes: ops.map((operator, i) => ({
        id: `c${i}`,
        type: 'condition' as const,
        position: { x: 0, y: 0 },
        data: { deviceId: 'fuellstand', operator, value: 3 },
      })),
      edges: [],
    })
    expect(def.blocks.map((b) => b.params.operator)).toEqual(['==', '!=', '>', '>=', '<', '<='])
  })
})

describe('fromBackendDefinition', () => {
  it('ist die Umkehrung von toBackendDefinition (Roundtrip ohne Verlust)', () => {
    const back = fromBackendDefinition(toBackendDefinition(SAMPLE_WORKFLOW))
    expect(back.nodes).toEqual(SAMPLE_WORKFLOW.nodes)
    expect(back.edges).toEqual(SAMPLE_WORKFLOW.edges)
  })

  it('füllt fehlende Felder mit Standardwerten auf', () => {
    const back = fromBackendDefinition({
      blocks: [{ id: 'p', type: 'prompt', params: { prompt: 'x' }, position: null }],
      edges: [{ source: 'a', target: 'p', port: 'next' }],
    })
    expect(back.nodes[0]).toEqual({
      id: 'p',
      type: 'prompt',
      position: { x: 0, y: 0 },
      data: { prompt: 'x', skillId: null, timeoutS: 60, retries: 0 },
    })
    expect(back.edges[0]).toEqual({ id: 'e-a-next-p', source: 'a', target: 'p', sourceHandle: 'out' })
  })
})

describe('fromBackendWorkflow / IDs', () => {
  it('macht aus der numerischen Backend-ID eine String-ID', () => {
    const wf = fromBackendWorkflow({
      id: 7,
      name: 'Demo',
      created_at: '2026-11-21T10:00:00Z',
      updated_at: '2026-11-21T11:00:00Z',
      definition: { blocks: [], edges: [] },
    })
    expect(wf).toEqual({ schemaVersion: 1, id: '7', name: 'Demo', updated_at: '2026-11-21T11:00:00Z', nodes: [], edges: [] })
    expect(toBackendWorkflowId('7')).toBe(7)
    expect(toBackendWorkflowId(null)).toBeNull()
    expect(toBackendWorkflowId('wf-abc')).toBeNull()
  })
})

describe('fromBackendRun', () => {
  it('übersetzt Lauf und Protokoll (warning -> warn)', () => {
    const run = fromBackendRun(
      BackendRunSchema.parse({
        id: 3,
        workflow_id: null,
        status: 'running',
        api_mode: 'mock',
        active_block_id: 'greifen',
        started_at: '2026-11-21T10:00:00Z',
        finished_at: null,
        credits_estimate: 2,
        credits_used: 1,
        error: null,
        log: [
          { id: 1, timestamp: '2026-11-21T10:00:01Z', level: 'warning', block_id: 'greifen', api_status: 'failed', duration_ms: 3000, message: 'Versuch 1/2' },
        ],
        cursor: 1,
      }),
    )
    expect(run).toEqual({
      id: '3',
      workflowId: null,
      status: 'running',
      activeNodeId: 'greifen',
      startedAt: '2026-11-21T10:00:00Z',
      finishedAt: null,
      error: null,
      credits: { used: 1 },
      log: [{ ts: '2026-11-21T10:00:01Z', level: 'warn', nodeId: 'greifen', apiStatus: 'failed', durationMs: 3000, message: 'Versuch 1/2' }],
    })
  })
})
