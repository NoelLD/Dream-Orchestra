import { describe, expect, it } from 'vitest'
import { WorkflowDocumentSchema } from '@/api/contract'
import { DEFAULT_MOCK_DEVICES } from '@/api/mockClient'
import { SAMPLES, SAMPLE_WORKFLOW } from './sample'
import { validateWorkflow } from './validate'

describe('Demo-Workflow Pick-and-Place', () => {
  it('entspricht dem Vertrag', () => {
    expect(WorkflowDocumentSchema.safeParse(SAMPLE_WORKFLOW).success).toBe(true)
  })

  it('besteht die Prüfung vor dem Start', () => {
    expect(validateWorkflow(SAMPLE_WORKFLOW).issues).toEqual([])
  })

  it('verwendet nur Geräte, die es im Testmodus gibt', () => {
    const ids = new Set(DEFAULT_MOCK_DEVICES.map((d) => d.id))
    const used = SAMPLE_WORKFLOW.nodes.flatMap((n) => ('deviceId' in n.data ? [n.data.deviceId] : []))
    expect(used.filter((id) => !ids.has(id))).toEqual([])
  })
})

describe.each(SAMPLES.map((s) => [s.label, s.doc] as const))('Beispiel %s', (_, doc) => {
  it('entspricht dem Vertrag und besteht die Prüfung', () => {
    expect(WorkflowDocumentSchema.safeParse(doc).success).toBe(true)
    expect(validateWorkflow(doc).issues).toEqual([])
  })
  it('verwendet nur Geräte, die es im Testmodus gibt', () => {
    const ids = new Set(DEFAULT_MOCK_DEVICES.map((d) => d.id))
    const used = doc.nodes.flatMap((n) => ('deviceId' in n.data ? [n.data.deviceId] : []))
    expect(used.filter((id) => !ids.has(id))).toEqual([])
  })
})
