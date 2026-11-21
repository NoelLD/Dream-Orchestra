import { MarkerType, type Edge, type Node } from '@xyflow/react'
import type { NodeDataOf, SourceHandle, WorkflowDocument, WorkflowEdge, WorkflowNode, WorkflowNodeType } from '@/api/contract'

/** React-Flow-Knoten, typgebunden an den Blocktyp des Vertrags. */
export type FlowNode = { [K in WorkflowNodeType]: Node<NodeDataOf<K>, K> }[WorkflowNodeType]
export type FlowEdge = Edge

export const EDGE_DEFAULTS = {
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#334155' },
} satisfies Partial<Edge>

export function toFlowEdge(edge: WorkflowEdge): FlowEdge {
  return { ...edge, ...EDGE_DEFAULTS }
}

export function fromDocument(doc: WorkflowDocument): { nodes: FlowNode[]; edges: FlowEdge[] } {
  return {
    nodes: doc.nodes.map((n) => ({ id: n.id, type: n.type, position: { ...n.position }, data: structuredClone(n.data) }) as FlowNode),
    edges: doc.edges.map(toFlowEdge),
  }
}

/** Nur die Felder des Vertrags – Zusatzfelder von React Flow fallen weg. */
export function toDocument(name: string, nodes: FlowNode[], edges: FlowEdge[]): WorkflowDocument {
  return {
    schemaVersion: 1,
    name,
    nodes: nodes.map(
      (n) => ({ id: n.id, type: n.type, position: { x: n.position.x, y: n.position.y }, data: structuredClone(n.data) }) as WorkflowNode,
    ),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: (e.sourceHandle ?? 'out') as SourceHandle,
    })),
  }
}
