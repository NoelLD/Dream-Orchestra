import { addEdge, type Connection, type OnEdgesChange, type OnNodesChange, type XYPosition } from '@xyflow/react'
import { create } from 'zustand'
import type { NodeDataOf, Run, WorkflowDocument, WorkflowNodeType } from '@/api/contract'
import { BLOCKS } from './blocks'
import { EDGE_DEFAULTS, fromDocument, toDocument, type FlowEdge, type FlowNode } from './flow'
import { SAMPLE_WORKFLOW } from './sample'
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
  load: (doc: WorkflowDocument, workflowId?: string | null) => void
  toDocument: () => WorkflowDocument
}

export const useEditor = create<EditorState>()((set, get) => ({
  ...fromDocument(SAMPLE_WORKFLOW),
  name: SAMPLE_WORKFLOW.name,
  workflowId: null,
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
  load: (doc, workflowId = null) => set({ ...fromDocument(doc), name: doc.name, workflowId, selectedNodeId: null, issues: [] }),
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

export const useRunStore = create<RunState>()((set) => ({
  runId: null,
  run: null,
  pollIntervalMs: 1000,
  setRun: (run) => set({ run, runId: run?.id ?? null }),
  setPollInterval: (pollIntervalMs) => set({ pollIntervalMs }),
}))
