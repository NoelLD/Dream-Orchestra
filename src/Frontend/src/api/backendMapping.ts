/**
 * Übersetzung Editor-Format (contract.ts) <-> Backend-Vertrag (OpenAPI unter /docs, docs/api-contract.md).
 *
 * Das Frontend arbeitet intern mit React-Flow-Knoten (`nodes`, `data`, camelCase); das Backend speichert und
 * führt Workflows als `blocks`/`params` (snake_case) aus. Nur der realClient nutzt diese Datei.
 */
import { z } from 'zod'
import type {
  ComparisonOperator,
  DeviceValue,
  Run,
  RunLogEntry,
  SourceHandle,
  Workflow,
  WorkflowDocument,
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeType,
} from './contract'
import { WORKFLOW_SCHEMA_VERSION } from './contract'

// ---------------------------------------------------------------------------
// Wire-Schemas des Backends
// ---------------------------------------------------------------------------
const BackendBlockTypeSchema = z.enum(['start', 'prompt', 'wait_sensor', 'set_actuator', 'wait_time', 'condition', 'end'])
type BackendBlockType = z.infer<typeof BackendBlockTypeSchema>
const BackendPortSchema = z.enum(['next', 'true', 'false', 'error'])
type BackendPort = z.infer<typeof BackendPortSchema>
const BackendOperatorSchema = z.enum(['==', '!=', '>', '>=', '<', '<='])
type BackendOperator = z.infer<typeof BackendOperatorSchema>

export const BackendBlockSchema = z.object({
  id: z.string(),
  type: BackendBlockTypeSchema,
  params: z.record(z.string(), z.unknown()).default({}),
  position: z.object({ x: z.number(), y: z.number() }).nullable().optional(),
})
export const BackendEdgeSchema = z.object({
  id: z.string().nullable().optional(),
  source: z.string(),
  target: z.string(),
  port: BackendPortSchema.default('next'),
})
export const BackendDefinitionSchema = z.object({
  blocks: z.array(BackendBlockSchema),
  edges: z.array(BackendEdgeSchema),
})
export type BackendDefinition = z.infer<typeof BackendDefinitionSchema>

export const BackendWorkflowSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  definition: BackendDefinitionSchema,
})
export const BackendWorkflowSummarySchema = BackendWorkflowSchema.omit({ definition: true })

export const BackendRunSchema = z.object({
  id: z.number().int(),
  workflow_id: z.number().int().nullable(),
  status: z.enum(['running', 'paused', 'succeeded', 'failed', 'stopped']),
  api_mode: z.string(),
  active_block_id: z.string().nullable(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  credits_estimate: z.number(),
  credits_used: z.number(),
  error: z.string().nullable(),
  log: z.array(
    z.object({
      id: z.number().int(),
      timestamp: z.string(),
      level: z.string(),
      block_id: z.string().nullable(),
      api_status: z.string().nullable(),
      duration_ms: z.number().nullable(),
      message: z.string(),
    }),
  ),
  cursor: z.number().int(),
})
export type BackendRun = z.infer<typeof BackendRunSchema>

export const BackendValidationSchema = z.object({
  valid: z.boolean(),
  errors: z.array(z.object({ message: z.string(), block_id: z.string().nullable() })),
  warnings: z.array(z.object({ message: z.string(), block_id: z.string().nullable() })),
  credits_estimate: z.number(),
})
export type BackendValidation = z.infer<typeof BackendValidationSchema>

// ---------------------------------------------------------------------------
// Tabellen
// ---------------------------------------------------------------------------
const TYPE_TO_BACKEND: Record<WorkflowNodeType, BackendBlockType> = {
  start: 'start',
  prompt: 'prompt',
  waitSensor: 'wait_sensor',
  setActuator: 'set_actuator',
  wait: 'wait_time',
  condition: 'condition',
  end: 'end',
}
const TYPE_FROM_BACKEND = Object.fromEntries(Object.entries(TYPE_TO_BACKEND).map(([k, v]) => [v, k])) as Record<
  BackendBlockType,
  WorkflowNodeType
>

const HANDLE_TO_PORT: Record<SourceHandle, BackendPort> = { out: 'next', error: 'error', true: 'true', false: 'false' }
const PORT_TO_HANDLE: Record<BackendPort, SourceHandle> = { next: 'out', error: 'error', true: 'true', false: 'false' }

const OP_TO_BACKEND: Record<ComparisonOperator, BackendOperator> = {
  eq: '==',
  neq: '!=',
  gt: '>',
  gte: '>=',
  lt: '<',
  lte: '<=',
}
const OP_FROM_BACKEND = Object.fromEntries(Object.entries(OP_TO_BACKEND).map(([k, v]) => [v, k])) as Record<
  BackendOperator,
  ComparisonOperator
>

// ---------------------------------------------------------------------------
// Editor -> Backend
// ---------------------------------------------------------------------------
function paramsOf(node: WorkflowNode): Record<string, unknown> {
  const label = node.data.label ? { label: node.data.label } : {}
  switch (node.type) {
    case 'start':
    case 'end':
      return label
    case 'prompt':
      return {
        ...label,
        prompt: node.data.prompt,
        skill_id: node.data.skillId,
        timeout_s: node.data.timeoutS,
        retries: node.data.retries,
      }
    case 'waitSensor':
      return {
        ...label,
        device: node.data.deviceId,
        operator: OP_TO_BACKEND[node.data.operator],
        value: node.data.value,
        timeout_s: node.data.timeoutS,
      }
    case 'setActuator':
      return { ...label, device: node.data.deviceId, value: node.data.value }
    case 'wait':
      return { ...label, seconds: node.data.seconds }
    case 'condition':
      return { ...label, device: node.data.deviceId, operator: OP_TO_BACKEND[node.data.operator], value: node.data.value }
  }
}

export function toBackendDefinition(doc: Pick<WorkflowDocument, 'nodes' | 'edges'>): BackendDefinition {
  return {
    blocks: doc.nodes.map((node) => ({
      id: node.id,
      type: TYPE_TO_BACKEND[node.type],
      params: paramsOf(node),
      position: { x: node.position.x, y: node.position.y },
    })),
    edges: doc.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      port: HANDLE_TO_PORT[edge.sourceHandle],
    })),
  }
}

// ---------------------------------------------------------------------------
// Backend -> Editor
// ---------------------------------------------------------------------------
const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback)
const num = (v: unknown, fallback: number): number => (typeof v === 'number' ? v : fallback)
const numOrNull = (v: unknown): number | null => (typeof v === 'number' ? v : null)
const deviceValue = (v: unknown): DeviceValue => (typeof v === 'boolean' || typeof v === 'number' ? v : true)
const operator = (v: unknown): ComparisonOperator =>
  BackendOperatorSchema.safeParse(v).success ? OP_FROM_BACKEND[v as BackendOperator] : 'eq'

function nodeOf(block: z.infer<typeof BackendBlockSchema>): WorkflowNode {
  const p = block.params
  const base = { id: block.id, position: block.position ?? { x: 0, y: 0 } }
  const label = typeof p.label === 'string' ? { label: p.label } : {}
  switch (TYPE_FROM_BACKEND[block.type]) {
    case 'start':
      return { ...base, type: 'start', data: label }
    case 'end':
      return { ...base, type: 'end', data: label }
    case 'prompt':
      return {
        ...base,
        type: 'prompt',
        data: {
          ...label,
          prompt: str(p.prompt),
          skillId: numOrNull(p.skill_id),
          timeoutS: num(p.timeout_s, 60),
          retries: num(p.retries, 0),
        },
      }
    case 'waitSensor':
      return {
        ...base,
        type: 'waitSensor',
        data: {
          ...label,
          deviceId: str(p.device),
          operator: operator(p.operator),
          value: deviceValue(p.value),
          timeoutS: numOrNull(p.timeout_s),
        },
      }
    case 'setActuator':
      return { ...base, type: 'setActuator', data: { ...label, deviceId: str(p.device), value: deviceValue(p.value) } }
    case 'wait':
      return { ...base, type: 'wait', data: { ...label, seconds: num(p.seconds, 1) } }
    case 'condition':
      return {
        ...base,
        type: 'condition',
        data: { ...label, deviceId: str(p.device), operator: operator(p.operator), value: deviceValue(p.value) },
      }
  }
}

export function fromBackendDefinition(definition: BackendDefinition): Pick<WorkflowDocument, 'nodes' | 'edges'> {
  return {
    nodes: definition.blocks.map(nodeOf),
    edges: definition.edges.map(
      (edge): WorkflowEdge => ({
        id: edge.id ?? `e-${edge.source}-${edge.port}-${edge.target}`,
        source: edge.source,
        target: edge.target,
        sourceHandle: PORT_TO_HANDLE[edge.port],
      }),
    ),
  }
}

export function fromBackendWorkflow(wf: z.infer<typeof BackendWorkflowSchema>): Workflow {
  return {
    schemaVersion: WORKFLOW_SCHEMA_VERSION,
    id: String(wf.id),
    name: wf.name,
    updated_at: wf.updated_at,
    ...fromBackendDefinition(wf.definition),
  }
}

const LEVELS: Record<string, RunLogEntry['level']> = { info: 'info', warning: 'warn', warn: 'warn', error: 'error' }

export function fromBackendRun(run: BackendRun): Run {
  return {
    id: String(run.id),
    workflowId: run.workflow_id === null ? null : String(run.workflow_id),
    status: run.status,
    activeNodeId: run.active_block_id,
    startedAt: run.started_at,
    finishedAt: run.finished_at,
    error: run.error,
    credits: { used: run.credits_used },
    log: run.log.map((entry) => ({
      ts: entry.timestamp,
      level: LEVELS[entry.level] ?? 'info',
      nodeId: entry.block_id,
      apiStatus: entry.api_status,
      durationMs: entry.duration_ms,
      message: entry.message,
    })),
  }
}

/** Gespeicherte Workflow-ID des Frontends (String) für das Backend (Zahl). */
export function toBackendWorkflowId(id: string | null): number | null {
  if (id === null) return null
  const n = Number(id)
  return Number.isInteger(n) && n > 0 ? n : null
}
