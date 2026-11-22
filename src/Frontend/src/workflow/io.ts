import { WorkflowDocumentSchema, type WorkflowDocument } from '@/api/contract'

export type ParseResult = { ok: true; workflow: WorkflowDocument } | { ok: false; error: string }

export function serializeWorkflow(doc: WorkflowDocument): string {
  return JSON.stringify(doc, null, 2)
}

export function parseWorkflowJson(text: string): ParseResult {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return { ok: false, error: 'Die Datei ist kein gültiges JSON.' }
  }

  const parsed = WorkflowDocumentSchema.safeParse(raw)
  if (!parsed.success) {
    const details = parsed.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(Wurzel)'}: ${issue.message}`)
      .join('; ')
    return { ok: false, error: `Die Datei ist kein gültiger Workflow. ${details}` }
  }
  return { ok: true, workflow: parsed.data }
}
