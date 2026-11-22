import { describe, expect, it } from 'vitest'
import type { WorkflowDocument } from '@/api/contract'
import { estimateCredits } from './estimate'
import { SAMPLE_WORKFLOW } from './sample'

const P = { x: 0, y: 0 }
const prompt = (id: string, retries: number) =>
  ({ id, type: 'prompt', position: P, data: { prompt: 'x', skillId: null, timeoutS: 60, retries } }) as const

describe('Credit-Schätzung vor dem Start (F15)', () => {
  it('zählt pro Durchlauf jeden erreichbaren Prompt mal (1 + Wiederholungen)', () => {
    const doc: WorkflowDocument = {
      schemaVersion: 1,
      name: 't',
      nodes: [{ id: 's', type: 'start', position: P, data: {} }, prompt('a', 0), prompt('b', 2), prompt('lose', 5)],
      edges: [
        { id: '1', source: 's', target: 'a', sourceHandle: 'out' },
        { id: '2', source: 'a', target: 'b', sourceHandle: 'out' },
      ],
    }
    expect(estimateCredits(doc)).toEqual({ minPerPass: 2, maxPerPass: 4, hasLoop: false })
  })

  it('erkennt Schleifen, weil sich die Credits dann pro Durchlauf wiederholen', () => {
    expect(estimateCredits(SAMPLE_WORKFLOW)).toEqual({ minPerPass: 1, maxPerPass: 2, hasLoop: true })
  })
})

describe('Zellen-Tasks', () => {
  it('kosten keine Credits', async () => {
    const { CNC_WORKFLOW } = await import('./sample')
    const { MOCK_CELLS } = await import('@/api/cellsMock')
    const free = new Set(MOCK_CELLS.flatMap((c) => c.tasks.map((t) => t.prompt.toLowerCase())))
    expect(estimateCredits(CNC_WORKFLOW).maxPerPass).toBe(2)
    expect(estimateCredits(CNC_WORKFLOW, free).maxPerPass).toBe(0)
  })
})
