import type { SourceHandle, WorkflowDocument, WorkflowNodeType } from '@/api/contract'

export type ValidationIssue = { nodeId: string | null; message: string }
export type ValidationResult = { valid: boolean; issues: ValidationIssue[] }

export const HANDLE_LABELS: Record<SourceHandle, string> = {
  out: 'next',
  error: 'error',
  true: 'true',
  false: 'else',
}

/** Ausgänge, die verbunden sein müssen. "error" ist optional (ohne ihn bricht der Lauf ab). */
const REQUIRED_OUTPUTS: Record<WorkflowNodeType, SourceHandle[]> = {
  start: ['out'],
  prompt: ['out'],
  waitSensor: ['out'],
  setActuator: ['out'],
  wait: ['out'],
  condition: ['true', 'false'],
  end: [],
}

/** Schnelles Feedback im Frontend; das Backend prüft beim Start erneut. */
export function validateWorkflow(doc: WorkflowDocument): ValidationResult {
  const issues: ValidationIssue[] = []
  const starts = doc.nodes.filter((n) => n.type === 'start')

  if (starts.length === 0) issues.push({ nodeId: null, message: 'Es fehlt ein Start-Block.' })
  for (const extra of starts.slice(1)) issues.push({ nodeId: extra.id, message: 'Nur ein Start-Block ist erlaubt.' })

  // Erreichbarkeit vom (ersten) Start aus
  const reachable = new Set<string>()
  const queue = starts[0] ? [starts[0].id] : []
  while (queue.length > 0) {
    const id = queue.shift() as string
    if (reachable.has(id)) continue
    reachable.add(id)
    for (const edge of doc.edges) if (edge.source === id) queue.push(edge.target)
  }

  for (const node of doc.nodes) {
    if (node.type !== 'start' && starts.length > 0 && !reachable.has(node.id)) {
      issues.push({ nodeId: node.id, message: 'Block ist nicht mit dem Start verbunden.' })
    }
    for (const handle of REQUIRED_OUTPUTS[node.type]) {
      if (!doc.edges.some((e) => e.source === node.id && e.sourceHandle === handle)) {
        issues.push({ nodeId: node.id, message: `Ausgang „${HANDLE_LABELS[handle]}“ ist nicht verbunden.` })
      }
    }
    if (node.type === 'prompt' && node.data.prompt.trim() === '') {
      issues.push({ nodeId: node.id, message: 'Der Prompt ist leer.' })
    }
    if ((node.type === 'waitSensor' || node.type === 'setActuator' || node.type === 'condition') && node.data.deviceId.trim() === '') {
      issues.push({ nodeId: node.id, message: 'Kein Gerät gewählt.' })
    }
  }

  return { valid: issues.length === 0, issues }
}
