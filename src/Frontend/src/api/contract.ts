/**
 * Schnittstelle der Oberfläche (Editor-Format). Verbindlich für das Backend ist dessen OpenAPI-Schema
 * (http://localhost:8000/docs, Zusammenfassung in docs/api-contract.md). realClient.ts übersetzt zwischen
 * beiden Formaten über backendMapping.ts.
 *
 * Das Frontend spricht nur mit /api (Proxy: Vite im Dev, nginx in Prod); das Präfix bleibt erhalten,
 * das Backend antwortet unter /api/... (z. B. GET /api/skills).
 */
import { z } from 'zod'

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export const HealthSchema = z.object({
  status: z.string(),
  service: z.string(),
})
export type Health = z.infer<typeof HealthSchema>

// ---------------------------------------------------------------------------
// Skills – Felder exakt aus src/Backend/models/schema.sql (Tabelle skills)
// ---------------------------------------------------------------------------
/** Vorschlagswerte aus Konzept.md §5. Das Schema erlaubt beliebigen Text. */
export const SKILL_STATUS_SUGGESTIONS = ['Entwurf', 'Training', 'Bereit', 'Fehler'] as const

export const SkillSchema = z.object({
  id: z.number().int(),
  name: z.string().min(1),
  description: z.string(),
  /** SQLite CURRENT_TIMESTAMP, z. B. "2026-11-21 17:30:00" */
  created_at: z.string(),
  status: z.string(),
  fine_tuned_model: z.string().nullable(),
})
export type Skill = z.infer<typeof SkillSchema>

export const SkillInputSchema = z.object({
  name: z.string().trim().min(1, 'Name darf nicht leer sein'),
  description: z.string(),
  status: z.string().min(1).optional(),
  fine_tuned_model: z.string().nullable().optional(),
})
export type SkillInput = z.infer<typeof SkillInputSchema>

// ---------------------------------------------------------------------------
// Workflows
// ---------------------------------------------------------------------------
export const WORKFLOW_SCHEMA_VERSION = 1 as const

export const ComparisonOperatorSchema = z.enum(['eq', 'neq', 'gt', 'gte', 'lt', 'lte'])
export type ComparisonOperator = z.infer<typeof ComparisonOperatorSchema>

export const DeviceValueSchema = z.union([z.boolean(), z.number()])
export type DeviceValue = z.infer<typeof DeviceValueSchema>

const PositionSchema = z.object({ x: z.number(), y: z.number() })

const StartDataSchema = z.object({ label: z.string().optional() })
const PromptDataSchema = z.object({
  label: z.string().optional(),
  prompt: z.string(),
  /** optionaler Skill (fine-getuntes Modell); null = Dream-1-Basismodell */
  skillId: z.number().int().nullable(),
  /** Zeitlimit pro Versuch in Sekunden (F6) */
  timeoutS: z.number().positive(),
  /** zusätzliche Versuche bei Fehlschlag (F9) */
  retries: z.number().int().min(0),
})
const WaitSensorDataSchema = z.object({
  label: z.string().optional(),
  deviceId: z.string(),
  operator: ComparisonOperatorSchema,
  value: DeviceValueSchema,
  /** null = ohne Zeitlimit (F12) */
  timeoutS: z.number().positive().nullable(),
})
const SetActuatorDataSchema = z.object({
  label: z.string().optional(),
  deviceId: z.string(),
  value: DeviceValueSchema,
})
const WaitDataSchema = z.object({
  label: z.string().optional(),
  seconds: z.number().positive(),
})
const ConditionDataSchema = z.object({
  label: z.string().optional(),
  deviceId: z.string(),
  operator: ComparisonOperatorSchema,
  value: DeviceValueSchema,
})
const EndDataSchema = z.object({ label: z.string().optional() })

const nodeBase = { id: z.string().min(1), position: PositionSchema }

export const WorkflowNodeSchema = z.discriminatedUnion('type', [
  z.object({ ...nodeBase, type: z.literal('start'), data: StartDataSchema }),
  z.object({ ...nodeBase, type: z.literal('prompt'), data: PromptDataSchema }),
  z.object({ ...nodeBase, type: z.literal('waitSensor'), data: WaitSensorDataSchema }),
  z.object({ ...nodeBase, type: z.literal('setActuator'), data: SetActuatorDataSchema }),
  z.object({ ...nodeBase, type: z.literal('wait'), data: WaitDataSchema }),
  z.object({ ...nodeBase, type: z.literal('condition'), data: ConditionDataSchema }),
  z.object({ ...nodeBase, type: z.literal('end'), data: EndDataSchema }),
])
export type WorkflowNode = z.infer<typeof WorkflowNodeSchema>
export type WorkflowNodeType = WorkflowNode['type']
export type NodeDataOf<T extends WorkflowNodeType> = Extract<WorkflowNode, { type: T }>['data']

/**
 * Ausgänge (sourceHandle):
 *  - "out":   Standardausgang (start, waitSensor-Erfolg, setActuator, wait, prompt-Erfolg)
 *  - "error": Fehlerpfad (prompt nach allen Versuchen, waitSensor nach Zeitlimit)
 *  - "true" / "false": Bedingung (A „wahr“ / B „sonst“)
 */
export const SourceHandleSchema = z.enum(['out', 'error', 'true', 'false'])
export type SourceHandle = z.infer<typeof SourceHandleSchema>

export const WorkflowEdgeSchema = z.object({
  id: z.string().min(1),
  source: z.string().min(1),
  target: z.string().min(1),
  sourceHandle: SourceHandleSchema,
})
export type WorkflowEdge = z.infer<typeof WorkflowEdgeSchema>

/** Inhalt eines Workflows – identisch mit dem JSON-Export (F3). */
export const WorkflowDocumentSchema = z.object({
  schemaVersion: z.literal(WORKFLOW_SCHEMA_VERSION),
  name: z.string().min(1),
  nodes: z.array(WorkflowNodeSchema),
  edges: z.array(WorkflowEdgeSchema),
})
export type WorkflowDocument = z.infer<typeof WorkflowDocumentSchema>

export const WorkflowSchema = WorkflowDocumentSchema.extend({
  id: z.string().min(1),
  updated_at: z.string(),
})
export type Workflow = z.infer<typeof WorkflowSchema>

export const WorkflowSummarySchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  updated_at: z.string(),
})
export type WorkflowSummary = z.infer<typeof WorkflowSummarySchema>

// ---------------------------------------------------------------------------
// Läufe (Runs) – die Ablauf-Engine läuft im Backend (N3)
// ---------------------------------------------------------------------------
export const RunStatusSchema = z.enum(['queued', 'running', 'paused', 'succeeded', 'failed', 'stopped'])
export type RunStatus = z.infer<typeof RunStatusSchema>
export const TERMINAL_RUN_STATUSES: readonly RunStatus[] = ['succeeded', 'failed', 'stopped']

export const LogLevelSchema = z.enum(['info', 'warn', 'error'])

export const RunLogEntrySchema = z.object({
  /** ISO-8601-Zeitstempel */
  ts: z.string(),
  level: LogLevelSchema,
  nodeId: z.string().nullable(),
  /** Status der Dream-Labs-API für diesen Schritt, z. B. "running", "succeeded", "timeout" */
  apiStatus: z.string().nullable(),
  /** Dauer des Schritts in ms (sobald bekannt) */
  durationMs: z.number().nullable(),
  message: z.string(),
})
export type RunLogEntry = z.infer<typeof RunLogEntrySchema>

export const RunSchema = z.object({
  id: z.string().min(1),
  workflowId: z.string().nullable(),
  status: RunStatusSchema,
  /** aktuell ausgeführter Block (F5) */
  activeNodeId: z.string().nullable(),
  startedAt: z.string(),
  finishedAt: z.string().nullable(),
  error: z.string().nullable(),
  credits: z.object({
    used: z.number().min(0),
  }),
  log: z.array(RunLogEntrySchema),
})
export type Run = z.infer<typeof RunSchema>

export const StartRunRequestSchema = z.object({
  /** gespeicherter Workflow, falls vorhanden (für Zuordnung) */
  workflowId: z.string().nullable(),
  /** Momentaufnahme des Workflows, der ausgeführt wird */
  workflow: WorkflowDocumentSchema,
})
export type StartRunRequest = z.infer<typeof StartRunRequestSchema>

// ---------------------------------------------------------------------------
// Geräte (F10/F11) – für den Hackathon nur Adapter "virtual"
// ---------------------------------------------------------------------------
export const DeviceKindSchema = z.enum(['sensor', 'actuator'])
export const DeviceTypeSchema = z.enum(['switch', 'button', 'number', 'lamp', 'conveyor'])
export type DeviceType = z.infer<typeof DeviceTypeSchema>

export const DeviceSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  kind: DeviceKindSchema,
  type: DeviceTypeSchema,
  adapter: z.string(),
  value: DeviceValueSchema,
  unit: z.string().nullable().optional(),
  min: z.number().nullable().optional(),
  max: z.number().nullable().optional(),
})
export type Device = z.infer<typeof DeviceSchema>

export const SetDeviceRequestSchema = z.object({ value: DeviceValueSchema })

// ---------------------------------------------------------------------------
// Fehlerformat
// ---------------------------------------------------------------------------
/** `{error: "<code>", detail: "<Text>", details?: ...}` – bei 422 vor dem Start enthält `details` das Prüfergebnis. */
export const ApiErrorBodySchema = z.object({
  error: z.string(),
  detail: z.string().optional(),
  details: z.unknown().optional(),
})

// ---------------------------------------------------------------------------
// Status des Backends (Banner „SIMULIERTE API“, N2)
// ---------------------------------------------------------------------------
export const BackendStatusSchema = z.object({
  version: z.string(),
  /** mock = Stellvertreter im Backend, sim = Simulation ohne Dream-1, real = Dream-1 (kostet Credits) */
  api_mode: z.string(),
  banner: z.string(),
  dream_api_key_set: z.boolean(),
  simulation_reachable: z.boolean().nullable(),
  problems: z.array(z.string()),
})
export type BackendStatus = z.infer<typeof BackendStatusSchema>

// ---------------------------------------------------------------------------
// Client-Schnittstelle – identisch für "real" und "mock" (N2)
// ---------------------------------------------------------------------------
export type ApiMode = 'mock' | 'real'

/** Prüfergebnis (F4) mit Problemen pro Block. */
export type RemoteValidation = { valid: boolean; issues: { nodeId: string | null; message: string }[]; creditsEstimate: number }

export interface ApiClient {
  readonly mode: ApiMode
  health(): Promise<Health>
  status(): Promise<BackendStatus>

  listSkills(): Promise<Skill[]>
  createSkill(input: SkillInput): Promise<Skill>
  updateSkill(id: number, input: SkillInput): Promise<Skill>
  /** Fehlende Skills aus dem Simulationsdienst anlegen (Namen passen dann zur Simulation). */
  importSimulationSkills(): Promise<Skill[]>

  /** Prüfung vor dem Start durch das Backend (kennt Geräte, Skills und API-Modus). */
  validateWorkflow(doc: WorkflowDocument): Promise<RemoteValidation>

  listWorkflows(): Promise<WorkflowSummary[]>
  getWorkflow(id: string): Promise<Workflow>
  createWorkflow(doc: WorkflowDocument): Promise<Workflow>
  updateWorkflow(id: string, doc: WorkflowDocument): Promise<Workflow>
  /** Läufe des Workflows bleiben im Backend erhalten (ohne Zuordnung). */
  deleteWorkflow(id: string): Promise<void>

  startRun(request: StartRunRequest): Promise<Run>
  getRun(id: string): Promise<Run>
  stopRun(id: string): Promise<Run>
  /** S (F8) */
  pauseRun(id: string): Promise<Run>
  resumeRun(id: string): Promise<Run>
  stepRun(id: string): Promise<Run>

  listDevices(): Promise<Device[]>
  setDevice(id: string, value: DeviceValue): Promise<Device>
}
