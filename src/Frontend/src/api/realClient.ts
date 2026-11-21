import { z } from 'zod'
import {
  ApiErrorBodySchema,
  DeviceSchema,
  HealthSchema,
  RunSchema,
  SkillSchema,
  WorkflowSchema,
  WorkflowSummarySchema,
  type ApiClient,
} from './contract'

export class ApiError extends Error {
  readonly status: number | null
  constructor(message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const BASE = '/api'

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
      const reason = parsedError.success ? parsedError.data.error : response.statusText || 'unbekannter Fehler'
      throw new ApiError(`${method} ${BASE}${path} fehlgeschlagen (HTTP ${response.status}): ${reason}`, response.status)
    }

    const parsed = schema.safeParse(payload)
    if (!parsed.success) {
      const first = parsed.error.issues[0]
      const where = first ? `${first.path.join('.') || '(Wurzel)'}: ${first.message}` : ''
      throw new ApiError(`Antwort von ${method} ${BASE}${path} entspricht nicht dem API-Vertrag (${where}).`, response.status)
    }
    return parsed.data
  }

  return {
    mode: 'real',
    health: () => request(HealthSchema, 'GET', '/health'),

    listSkills: () => request(z.array(SkillSchema), 'GET', '/skills'),
    createSkill: (input) => request(SkillSchema, 'POST', '/skills', input),
    updateSkill: (id, input) => request(SkillSchema, 'PUT', `/skills/${id}`, input),

    listWorkflows: () => request(z.array(WorkflowSummarySchema), 'GET', '/workflows'),
    getWorkflow: (id) => request(WorkflowSchema, 'GET', `/workflows/${encodeURIComponent(id)}`),
    createWorkflow: (doc) => request(WorkflowSchema, 'POST', '/workflows', doc),
    updateWorkflow: (id, doc) => request(WorkflowSchema, 'PUT', `/workflows/${encodeURIComponent(id)}`, doc),

    startRun: (req) => request(RunSchema, 'POST', '/runs', req),
    getRun: (id) => request(RunSchema, 'GET', `/runs/${encodeURIComponent(id)}`),
    stopRun: (id) => request(RunSchema, 'POST', `/runs/${encodeURIComponent(id)}/stop`),
    pauseRun: (id) => request(RunSchema, 'POST', `/runs/${encodeURIComponent(id)}/pause`),
    resumeRun: (id) => request(RunSchema, 'POST', `/runs/${encodeURIComponent(id)}/resume`),
    stepRun: (id) => request(RunSchema, 'POST', `/runs/${encodeURIComponent(id)}/step`),

    listDevices: () => request(z.array(DeviceSchema), 'GET', '/devices'),
    setDevice: (id, value) => request(DeviceSchema, 'PUT', `/devices/${encodeURIComponent(id)}`, { value }),
  }
}
