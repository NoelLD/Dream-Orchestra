import { describe, expect, it } from 'vitest'
import type { WorkflowDocument } from '@/api/contract'
import { parseWorkflowJson, serializeWorkflow } from './io'

const pickAndPlace: WorkflowDocument = {
  schemaVersion: 1,
  name: 'Pick-and-Place',
  nodes: [
    { id: 'start', type: 'start', position: { x: 0, y: 0 }, data: {} },
    {
      id: 'greifen',
      type: 'prompt',
      position: { x: 200, y: 0 },
      data: { prompt: 'Greife das Objekt', skillId: null, timeoutS: 60, retries: 1 },
    },
    {
      id: 'sensor',
      type: 'waitSensor',
      position: { x: 400, y: 0 },
      data: { deviceId: 'lichtschranke', operator: 'eq', value: true, timeoutS: null },
    },
    {
      id: 'mehr',
      type: 'condition',
      position: { x: 600, y: 0 },
      data: { deviceId: 'weitere-objekte', operator: 'eq', value: true },
    },
    { id: 'ende', type: 'end', position: { x: 800, y: 0 }, data: {} },
  ],
  edges: [
    { id: 'e1', source: 'start', target: 'greifen', sourceHandle: 'out' },
    { id: 'e2', source: 'greifen', target: 'sensor', sourceHandle: 'out' },
    { id: 'e3', source: 'sensor', target: 'mehr', sourceHandle: 'out' },
    { id: 'e4', source: 'mehr', target: 'greifen', sourceHandle: 'true' },
    { id: 'e5', source: 'mehr', target: 'ende', sourceHandle: 'false' },
  ],
}

describe('Workflow-Import/-Export (F3)', () => {
  it('liefert nach Export und Import einen identischen Workflow', () => {
    const result = parseWorkflowJson(serializeWorkflow(pickAndPlace))
    expect(result).toEqual({ ok: true, workflow: pickAndPlace })
  })

  it('meldet ungültiges JSON verständlich', () => {
    const result = parseWorkflowJson('{ kein json')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toMatch(/kein gültiges JSON/)
  })

  it('nennt das fehlerhafte Feld, wenn das Schema verletzt ist', () => {
    const broken = { ...pickAndPlace, nodes: [{ id: 'x', type: 'prompt', position: { x: 0, y: 0 }, data: {} }] }
    const result = parseWorkflowJson(JSON.stringify(broken))
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain('nodes.0.data.prompt')
  })

  it('lehnt unbekannte Schema-Versionen ab', () => {
    const result = parseWorkflowJson(JSON.stringify({ ...pickAndPlace, schemaVersion: 99 }))
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain('schemaVersion')
  })
})
