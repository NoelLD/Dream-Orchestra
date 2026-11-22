import { addEdge, type Connection, type OnEdgesChange, type OnNodesChange, type XYPosition } from '@xyflow/react'
import { create } from 'zustand'
import { TERMINAL_RUN_STATUSES, type NodeDataOf, type Run, type WorkflowDocument, type WorkflowNodeType } from '@/api/contract'
import { BLOCKS } from './blocks'
import { EDGE_DEFAULTS, fromDocument, toDocument, type FlowEdge, type FlowNode } from './flow'
import { serializeWorkflow } from './io'
import { EMPTY_WORKFLOW, SAMPLE_WORKFLOW } from './sample'
import type { ValidationIssue } from './validate'

let idCounter = 0
const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(idCounter++).toString(36)}`

type EditorState = {
  name: string
  workflowId: string | null
  nodes: FlowNode[]
  edges: FlowEdge[]
  selectedNodeId: string | null
  issues: ValidationIssue[]

  onNodesChange: OnNodesChange<FlowNode>
  onEdgesChange: OnEdgesChange<FlowEdge>
  onConnect: (connection: Connection) => void
  addBlock: (type: WorkflowNodeType, position: XYPosition) => string
  updateData: <T extends WorkflowNodeType>(id: string, patch: Partial<NodeDataOf<T>>) => void
  removeNode: (id: string) => void
  select: (id: string | null) => void
  setName: (name: string) => void
  setIssues: (issues: ValidationIssue[]) => void
  /** Stand beim letzten Laden/Speichern (serialisiert) – Grundlage für „ungespeicherte Änderungen“ */
  savedJson: string
  load: (doc: WorkflowDocument, workflowId?: string | null) => void
  /** Nach erfolgreichem Speichern: ID übernehmen, aktuellen Stand als gespeichert merken */
  markSaved: (workflowId: string) => void
  /** Neuer, leerer Workflow (Start → Ende), noch nicht gespeichert */
  newWorkflow: () => void
  /** Zuordnung lösen (z. B. nachdem der geöffnete Workflow gelöscht wurde); Inhalt bleibt */
  detach: () => void
  toDocument: () => WorkflowDocument
}

/** Editorzustand eines Dokuments inkl. Vergleichsstand (Roundtrip über toDocument, damit „unverändert“ exakt ist). */
function loaded(doc: WorkflowDocument, workflowId: string | null) {
  const flow = fromDocument(doc)
  return { ...flow, name: doc.name, workflowId, savedJson: serializeWorkflow(toDocument(doc.name, flow.nodes, flow.edges)) }
}

export const selectIsDirty = (s: Pick<EditorState, 'toDocument' | 'savedJson'>) =>
  serializeWorkflow(s.toDocument()) !== s.savedJson

export const useEditor = create<EditorState>()((set, get) => ({
  ...loaded(SAMPLE_WORKFLOW, null),
  selectedNodeId: null,
  issues: [],

  onNodesChange: (changes) => set((s) => ({ nodes: changes.applyTo(s.nodes) })),
  onEdgesChange: (changes) => set((s) => ({ edges: changes.applyTo(s.edges) })),
  onConnect: (connection) =>
    set((s) => {
      // Pro Ausgang nur eine Kante: eine neue Verbindung ersetzt die alte.
      const rest = s.edges.filter((e) => !(e.source === connection.source && e.sourceHandle === connection.sourceHandle))
      return { edges: addEdge({ ...connection, ...EDGE_DEFAULTS, id: newId('e') }, rest), issues: [] }
    }),
  addBlock: (type, position) => {
    const id = newId(type)
    const node = { id, type, position, data: BLOCKS[type].defaultData() } as FlowNode
    set((s) => ({ nodes: [...s.nodes, node], selectedNodeId: id, issues: [] }))
    return id
  },
  updateData: (id, patch) =>
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === id ? ({ ...n, data: { ...n.data, ...patch } } as FlowNode) : n)),
      issues: s.issues.filter((i) => i.nodeId !== id),
    })),
  removeNode: (id) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
      selectedNodeId: s.selectedNodeId === id ? null : s.selectedNodeId,
    })),
  select: (id) => set({ selectedNodeId: id }),
  setName: (name) => set({ name }),
  setIssues: (issues) => set({ issues }),
  load: (doc, workflowId = null) => set({ ...loaded(doc, workflowId), selectedNodeId: null, issues: [] }),
  markSaved: (workflowId) => set({ workflowId, savedJson: serializeWorkflow(get().toDocument()) }),
  newWorkflow: () => set({ ...loaded(EMPTY_WORKFLOW, null), selectedNodeId: null, issues: [] }),
  detach: () => set({ workflowId: null, savedJson: '' }),
  toDocument: () => toDocument(get().name, get().nodes, get().edges),
}))

// ---------------------------------------------------------------------------
// Laufzustand (nur Anzeige – die Engine läuft im Backend, N3)
// ---------------------------------------------------------------------------
export const POLL_INTERVAL_OPTIONS = [500, 1000, 2000, 5000] as const

type RunState = {
  runId: string | null
  run: Run | null
  pollIntervalMs: number
  setRun: (run: Run | null) => void
  setPollInterval: (ms: number) => void
}

// Die ID eines aktiven Laufs übersteht ein Neuladen der Seite: Abfrage und STOP finden den Lauf wieder.
const ACTIVE_RUN_KEY = 'dreamorchestra.activeRunId'

export function restoredRunId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_RUN_KEY)
  } catch {
    return null
  }
}

function rememberRunId(run: Run | null) {
  try {
    if (run && !TERMINAL_RUN_STATUSES.includes(run.status)) localStorage.setItem(ACTIVE_RUN_KEY, run.id)
    else localStorage.removeItem(ACTIVE_RUN_KEY)
  } catch {
    // ohne Speicher (privates Fenster): Lauf nur bis zum Neuladen bekannt
  }
}

export const useRunStore = create<RunState>()((set) => ({
  runId: restoredRunId(),
  run: null,
  pollIntervalMs: 1000,
  setRun: (run) => {
    rememberRunId(run)
    set({ run, runId: run?.id ?? null })
  },
  setPollInterval: (pollIntervalMs) => set({ pollIntervalMs }),
}))
