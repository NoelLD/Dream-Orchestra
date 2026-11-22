import type { WorkflowDocument } from '@/api/contract'

/**
 * Credits pro Durchlauf: min = jeder erreichbare Prompt einmal, max = inklusive aller
 * Wiederholungen. Bei Schleifen fällt das pro Schleifendurchlauf erneut an.
 */
export type CreditEstimate = { minPerPass: number; maxPerPass: number; hasLoop: boolean }

/** freePrompts: Prompts von Zellen-Tasks (klein geschrieben); sie laufen geskriptet und kosten nichts. */
export function estimateCredits(doc: WorkflowDocument, freePrompts: ReadonlySet<string> = new Set()): CreditEstimate {
  const start = doc.nodes.find((n) => n.type === 'start')
  if (!start) return { minPerPass: 0, maxPerPass: 0, hasLoop: false }

  const successors = (id: string) => doc.edges.filter((e) => e.source === id).map((e) => e.target)
  const state = new Map<string, 'visiting' | 'done'>()
  let hasLoop = false

  const visit = (id: string) => {
    const s = state.get(id)
    if (s === 'visiting') hasLoop = true
    if (s) return
    state.set(id, 'visiting')
    for (const next of successors(id)) visit(next)
    state.set(id, 'done')
  }
  visit(start.id)

  let minPerPass = 0
  let maxPerPass = 0
  for (const node of doc.nodes) {
    if (node.type === 'prompt' && state.has(node.id) && !freePrompts.has(node.data.prompt.trim().toLowerCase())) {
      minPerPass += 1
      maxPerPass += 1 + node.data.retries
    }
  }
  return { minPerPass, maxPerPass, hasLoop }
}
