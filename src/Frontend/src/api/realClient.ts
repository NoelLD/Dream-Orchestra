import { z } from 'zod'
import {
  BackendRunSchema,
  BackendValidationSchema,
  BackendWorkflowSchema,
  BackendWorkflowSummarySchema,
  fromBackendRun,
  fromBackendWorkflow,
  toBackendDefinition,
  toBackendWorkflowId,
  type BackendValidation,
} from './backendMapping'
import {
  ApiErrorBodySchema,
  BackendStatusSchema,
  CellResultsSchema,
  CellSchema,
  CellSessionSchema,
  DeviceSchema,
  RobotSchema,
  HealthSchema,
  SkillSchema,
  type ApiClient,
  type RemoteValidation,
  type WorkflowDocument,
} from './contract'

export class ApiError extends Error {
  readonly status: number | null
  /** Fehlercode des Backends, z. B. "invalid", "conflict", "simulation_unavailable" */
  readonly code: string | null
  /** Zusatzdaten, z. B. das Prüfergebnis bei 422 vor dem Start */
  readonly details: unknown
  constructor(message: string, status: number | null, code: string | null = null, details: unknown = undefined) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

const BASE = '/api'

export function toRemoteValidation(v: BackendValidation): RemoteValidation {
  return {
    valid: v.valid,
    issues: v.errors.map((e) => ({ nodeId: e.block_id, message: e.message })),
    creditsEstimate: v.credits_estimate,
  }
}

/** Prüfergebnis aus einem 422 beim Start, falls vorhanden. */
export function validationFromError(error: unknown): RemoteValidation | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null
  const parsed = BackendValidationSchema.safeParse(error.details)
  return parsed.success ? toRemoteValidation(parsed.data) : null
}

const workflowBody = (doc: WorkflowDocument) => ({ name: doc.name, definition: toBackendDefinition(doc) })

export function createRealClient(fetchFn: typeof fetch = (...args) => fetch(...args)): ApiClient {
  async function request<T>(schema: z.ZodType<T>, method: string, path: string, body?: unknown): Promise<T> {
    let response: Response
    try {
      response = await fetchFn(`${BASE}${path}`, {
        method,
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch {
      throw new ApiError(`Backend nicht erreichbar (${method} ${BASE}${path}).`, null)
    }

    const payload: unknown = await response.json().catch(() => undefined)

    if (!response.ok) {
      const parsedError = ApiErrorBodySchema.safeParse(payload)
      const reason = parsedError.success
        ? (parsedError.data.detail ?? parsedError.data.error)
        : response.statusText || 'unbekannter Fehler'
      throw new ApiError(
        `${method} ${BASE}${path} fehlgeschlagen (HTTP ${response.status}): ${reason}`,
        response.status,
        parsedError.success ? parsedError.data.error : null,
        parsedError.success ? parsedError.data.details : undefined,
      )
    }

    const parsed = schema.safeParse(payload)
    if (!parsed.success) {
      const first = parsed.error.issues[0]
      const where = first ? `${first.path.join('.') || '(Wurzel)'}: ${first.message}` : ''
      throw new ApiError(`Antwort von ${method} ${BASE}${path} entspricht nicht dem API-Vertrag (${where}).`, response.status)
    }
    return parsed.data
  }

  const run = (method: string, path: string, body?: unknown) =>
    request(BackendRunSchema, method, path, body).then(fromBackendRun)
  const workflow = (method: string, path: string, body?: unknown) =>
    request(BackendWorkflowSchema, method, path, body).then(fromBackendWorkflow)
  const id = (value: string) => encodeURIComponent(value)

  return {
    mode: 'real',
    health: () => request(HealthSchema, 'GET', '/health'),
    status: () => request(BackendStatusSchema, 'GET', '/status'),

    listSkills: () => request(z.array(SkillSchema), 'GET', '/skills'),
    createSkill: (input) => request(SkillSchema, 'POST', '/skills', input),
    updateSkill: (skillId, input) => request(SkillSchema, 'PUT', `/skills/${skillId}`, input),
    importSimulationSkills: () => request(z.array(SkillSchema), 'POST', '/skills/import-simulation'),

    validateWorkflow: (doc) =>
      request(BackendValidationSchema, 'POST', '/workflows/validate', toBackendDefinition(doc)).then(toRemoteValidation),
    listWorkflows: () =>
      request(z.array(BackendWorkflowSummarySchema), 'GET', '/workflows').then((list) =>
        list.map((w) => ({ id: String(w.id), name: w.name, updated_at: w.updated_at })),
      ),
    getWorkflow: (workflowId) => workflow('GET', `/workflows/${id(workflowId)}`),
    createWorkflow: (doc) => workflow('POST', '/workflows', workflowBody(doc)),
    updateWorkflow: (workflowId, doc) => workflow('PUT', `/workflows/${id(workflowId)}`, workflowBody(doc)),
    deleteWorkflow: (workflowId) => request(z.undefined(), 'DELETE', `/workflows/${id(workflowId)}`),

    startRun: (req) =>
      run('POST', '/runs', { workflow_id: toBackendWorkflowId(req.workflowId), definition: toBackendDefinition(req.workflow) }),
    getRun: (runId) => run('GET', `/runs/${id(runId)}`),
    stopRun: (runId) => run('POST', `/runs/${id(runId)}/stop`),
    pauseRun: (runId) => run('POST', `/runs/${id(runId)}/pause`),
    resumeRun: (runId) => run('POST', `/runs/${id(runId)}/resume`),
    stepRun: (runId) => run('POST', `/runs/${id(runId)}/step`),

    listDevices: () => request(z.array(DeviceSchema), 'GET', '/devices'),
    setDevice: (deviceId, value) => request(DeviceSchema, 'PUT', `/devices/${id(deviceId)}/value`, { value }),
    createDevice: (input) => request(DeviceSchema, 'POST', '/devices', input),
    updateDevice: (deviceId, input) => request(DeviceSchema, 'PUT', `/devices/${id(deviceId)}`, input),
    deleteDevice: (deviceId) => request(z.undefined(), 'DELETE', `/devices/${id(deviceId)}`),

    listCells: () => request(z.array(CellSchema), 'GET', '/cells'),
    startCellSession: (cell) => request(z.unknown(), 'POST', `/cells/${id(cell)}/session`).then(() => undefined),
    getCellSession: () =>
      request(CellSessionSchema, 'GET', '/cells/session').catch((error: unknown) => {
        if (error instanceof ApiError && error.code === 'no_session') return null
        throw error
      }),
    cellAction: (action) => request(z.unknown(), 'POST', '/cells/session/action', { action }).then(() => undefined),
    cellTask: (task, seed) =>
      request(z.unknown(), 'POST', '/cells/session/task', seed === undefined ? { task } : { task, seed }).then(() => undefined),
    endCellSession: () => request(z.undefined(), 'DELETE', '/cells/session'),
    cellFrameUrl: (view, tick) => `${BASE}/cells/session/frame.jpg?view=${view}&t=${tick}`,

    listRobots: () => request(z.array(RobotSchema), 'GET', '/simulation/robots'),
    getCellResults: () => request(CellResultsSchema, 'GET', '/results/cells'),
  }
}
