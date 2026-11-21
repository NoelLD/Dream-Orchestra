import { describe, expect, it } from 'vitest'
import type { WorkflowDocument } from '@/api/contract'
import { fromDocument, toDocument } from './flow'
import { parseWorkflowJson, serializeWorkflow } from './io'

const sample: WorkflowDocument = {
  schemaVersion: 1,
  name: 'Beispiel',
  nodes: [
    { id: 's', type: 'start', position: { x: 0, y: 0 }, data: {} },
    { id: 'p', type: 'prompt', position: { x: 220, y: 0 }, data: { label: 'Greifen', prompt: 'Greifen', skillId: null, timeoutS: 60, retries: 0 } },
    { id: 'w', type: 'waitSensor', position: { x: 440, y: 0 }, data: { deviceId: 'lichtschranke', operator: 'eq', value: true, timeoutS: 30 } },
    { id: 'c', type: 'condition', position: { x: 660, y: 0 }, data: { deviceId: 'weitere-objekte', operator: 'eq', value: true } },
    { id: 'e', type: 'end', position: { x: 880, y: 0 }, data: {} },
  ],
  edges: [
    { id: 'e1', source: 's', target: 'p', sourceHandle: 'out' },
    { id: 'e2', source: 'p', target: 'w', sourceHandle: 'out' },
    { id: 'e3', source: 'w', target: 'c', sourceHandle: 'out' },
    { id: 'e4', source: 'c', target: 'p', sourceHandle: 'true' },
    { id: 'e5', source: 'c', target: 'e', sourceHandle: 'false' },
  ],
}

describe('Editor-Zustand <-> Workflow-JSON', () => {
  it('erzeugt Kanten mit Pfeilspitze für den Editor', () => {
    const { edges } = fromDocument(sample)
    expect(edges[0]?.markerEnd).toBeDefined()
  })

  it('entfernt beim Export die Zusatzfelder von React Flow', () => {
    const flow = fromDocument(sample)
    const touched = {
      nodes: flow.nodes.map((n) => ({ ...n, selected: true, dragging: false, measured: { width: 180, height: 60 } })),
      edges: flow.edges.map((e) => ({ ...e, selected: true, animated: true })),
    }
    expect(toDocument(sample.name, touched.nodes, touched.edges)).toEqual(sample)
  })

  it('ist nach Export und Import identisch mit dem Editor-Workflow (Phase-7-Nachweis)', () => {
    const flow = fromDocument(sample)
    const exported = serializeWorkflow(toDocument(sample.name, flow.nodes, flow.edges))
    const imported = parseWorkflowJson(exported)
    expect(imported.ok).toBe(true)
    if (!imported.ok) return
    const reloaded = fromDocument(imported.workflow)
    expect(toDocument(imported.workflow.name, reloaded.nodes, reloaded.edges)).toEqual(sample)
  })
})
