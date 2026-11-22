import { beforeEach, describe, expect, it } from 'vitest'
import { EMPTY_WORKFLOW, SAMPLE_WORKFLOW } from './sample'
import { selectIsDirty, useEditor } from './store'

const state = () => useEditor.getState()

describe('Editor-Store: mehrere Workflows', () => {
  beforeEach(() => state().load(SAMPLE_WORKFLOW))

  it('ist nach dem Laden unverändert und erkennt Änderungen', () => {
    expect(selectIsDirty(state())).toBe(false)
    state().setName('Umbenannt')
    expect(selectIsDirty(state())).toBe(true)
  })

  it('erkennt Änderungen an Blöcken', () => {
    state().updateData<'prompt'>('greifen', { prompt: 'anders' })
    expect(selectIsDirty(state())).toBe(true)
  })

  it('merkt sich nach dem Speichern ID und Stand', () => {
    state().setName('Neu benannt')
    state().markSaved('42')
    expect(state().workflowId).toBe('42')
    expect(selectIsDirty(state())).toBe(false)
  })

  it('lädt einen gespeicherten Workflow mit seiner ID', () => {
    state().load({ ...SAMPLE_WORKFLOW, name: 'Zweiter' }, '7')
    expect(state().workflowId).toBe('7')
    expect(state().name).toBe('Zweiter')
    expect(selectIsDirty(state())).toBe(false)
  })

  it('„Neu“ legt einen leeren, gültigen Workflow ohne ID an', () => {
    state().markSaved('3')
    state().newWorkflow()
    expect(state().workflowId).toBeNull()
    expect(state().name).toBe(EMPTY_WORKFLOW.name)
    expect(state().nodes.map((n) => n.type)).toEqual(['start', 'end'])
    expect(state().edges).toHaveLength(1)
    expect(selectIsDirty(state())).toBe(false)
  })

  it('löst nach dem Löschen des geöffneten Workflows die Zuordnung, behält aber den Inhalt', () => {
    state().markSaved('5')
    state().detach()
    expect(state().workflowId).toBeNull()
    expect(state().nodes).toHaveLength(SAMPLE_WORKFLOW.nodes.length)
    expect(selectIsDirty(state())).toBe(true)
  })
})

describe('Laufzustand übersteht Neuladen (Codex: STOP nach Refresh)', () => {
  it('merkt sich die ID eines aktiven Laufs und vergisst sie am Ende', async () => {
    const { restoredRunId, useRunStore } = await import('./store')
    const run = { id: '42', status: 'running' } as unknown as Parameters<ReturnType<typeof useRunStore.getState>['setRun']>[0]
    useRunStore.getState().setRun(run)
    expect(restoredRunId()).toBe('42')
    useRunStore.getState().setRun({ ...run!, status: 'stopped' } as typeof run)
    expect(restoredRunId()).toBeNull()
  })
})
