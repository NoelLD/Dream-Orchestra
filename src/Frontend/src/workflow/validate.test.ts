import { describe, expect, it } from 'vitest'
import type { WorkflowDocument } from '@/api/contract'
import { validateWorkflow } from './validate'

const P = { x: 0, y: 0 }
const doc = (nodes: WorkflowDocument['nodes'], edges: WorkflowDocument['edges']): WorkflowDocument => ({
  schemaVersion: 1,
  name: 'Test',
  nodes,
  edges,
})
const start = { id: 's', type: 'start', position: P, data: {} } as const
const end = { id: 'e', type: 'end', position: P, data: {} } as const
const prompt = (id: string, text: string) =>
  ({ id, type: 'prompt', position: P, data: { prompt: text, skillId: null, timeoutS: 60, retries: 0 } }) as const

const messagesFor = (result: ReturnType<typeof validateWorkflow>, nodeId: string | null) =>
  result.issues.filter((i) => i.nodeId === nodeId).map((i) => i.message)

describe('Prüfung vor dem Start (F4)', () => {
  it('akzeptiert einen vollständig verbundenen Workflow', () => {
    const result = validateWorkflow(
      doc([start, prompt('p', 'Greife'), end], [
        { id: '1', source: 's', target: 'p', sourceHandle: 'out' },
        { id: '2', source: 'p', target: 'e', sourceHandle: 'out' },
      ]),
    )
    expect(result).toEqual({ valid: true, issues: [] })
  })

  it('verlangt genau einen Start-Block', () => {
    expect(messagesFor(validateWorkflow(doc([end], [])), null)).toContain('Es fehlt ein Start-Block.')
    const two = validateWorkflow(doc([start, { ...start, id: 's2' }], []))
    expect(messagesFor(two, 's2')).toContain('Nur ein Start-Block ist erlaubt.')
  })

  it('markiert Blöcke, die vom Start aus nicht erreichbar sind', () => {
    const result = validateWorkflow(
      doc([start, end, prompt('lose', 'x')], [{ id: '1', source: 's', target: 'e', sourceHandle: 'out' }]),
    )
    expect(result.valid).toBe(false)
    expect(messagesFor(result, 'lose')).toContain('Block ist nicht mit dem Start verbunden.')
  })

  it('markiert einen leeren Prompt am betroffenen Block', () => {
    const result = validateWorkflow(
      doc([start, prompt('p', '   '), end], [
        { id: '1', source: 's', target: 'p', sourceHandle: 'out' },
        { id: '2', source: 'p', target: 'e', sourceHandle: 'out' },
      ]),
    )
    expect(messagesFor(result, 'p')).toContain('Der Prompt ist leer.')
  })

  it('verlangt bei einer Bedingung beide Ausgänge', () => {
    const result = validateWorkflow(
      doc(
        [start, { id: 'c', type: 'condition', position: P, data: { deviceId: 'lichtschranke', operator: 'eq', value: true } }, end],
        [
          { id: '1', source: 's', target: 'c', sourceHandle: 'out' },
          { id: '2', source: 'c', target: 'e', sourceHandle: 'true' },
        ],
      ),
    )
    expect(messagesFor(result, 'c')).toContain('Ausgang „else“ ist nicht verbunden.')
  })

  it('verlangt ein gewähltes Gerät bei Sensor- und Aktor-Blöcken', () => {
    const result = validateWorkflow(
      doc([start, { id: 'a', type: 'setActuator', position: P, data: { deviceId: '', value: true } }, end], [
        { id: '1', source: 's', target: 'a', sourceHandle: 'out' },
        { id: '2', source: 'a', target: 'e', sourceHandle: 'out' },
      ]),
    )
    expect(messagesFor(result, 'a')).toContain('Kein Gerät gewählt.')
  })

  it('erlaubt Schleifen zurück zu früheren Blöcken', () => {
    const result = validateWorkflow(
      doc(
        [start, prompt('p', 'Greife'), { id: 'c', type: 'condition', position: P, data: { deviceId: 'weitere-objekte', operator: 'eq', value: true } }, end],
        [
          { id: '1', source: 's', target: 'p', sourceHandle: 'out' },
          { id: '2', source: 'p', target: 'c', sourceHandle: 'out' },
          { id: '3', source: 'c', target: 'p', sourceHandle: 'true' },
          { id: '4', source: 'c', target: 'e', sourceHandle: 'false' },
        ],
      ),
    )
    expect(result.valid).toBe(true)
  })
})
