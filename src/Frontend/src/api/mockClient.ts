/**
 * TESTMODUS (N2): spielt Backend-Antworten nach, damit ohne Credits und ohne fertiges
 * Backend entwickelt werden kann. Die Oberfläche zeigt dabei dauerhaft „SIMULIERTE API“.
 *
 * Achtung: Das ist ein Stellvertreter, nicht die Ablauf-Engine. Die echte Engine läuft im
 * Backend (N3). Der Fortschritt wird bei jeder Abfrage aus der vergangenen Zeit berechnet.
 */
import type {
  ApiClient,
  ComparisonOperator,
  Device,
  DeviceConfig,
  DeviceInput,
  DeviceValue,
  Run,
  RunLogEntry,
  Skill,
  SkillInput,
  Workflow,
  WorkflowDocument,
  WorkflowNode,
  SourceHandle,
} from './contract'
import { DEVICE_TYPE_KIND } from './contract'
import { estimateCredits } from '@/workflow/estimate'
import { validateWorkflow } from '@/workflow/validate'
import { createCellsMock } from './cellsMock'
import { ApiError } from './realClient'

export type MockOptions = {
  /** Uhr in Millisekunden (für Tests injizierbar) */
  now?: () => number
  /** wie lange ein simulierter Dream-1-Lauf dauert */
  promptDurationMs?: number
}

const MAX_TRANSITIONS_PER_POLL = 500

/** Skills des Simulationsdienstes (src/Simulation, GET /skills) – für „Aus Simulation übernehmen“ im Testmodus. */
export const MOCK_SIMULATION_SKILLS: readonly SkillInput[] = [
  { name: 'pick-banana', description: 'Pick up the banana', fine_tuned_model: null },
  { name: 'pick-apple', description: 'Pick up the apple', fine_tuned_model: null },
  { name: 'banana-to-plate', description: 'Put the banana on the plate', fine_tuned_model: null },
  { name: 'apple-to-bowl', description: 'Put the apple into the bowl', fine_tuned_model: null },
]

const VIRTUAL = { adapter: 'virtual', protocol: 'virtual', config: { protocol: 'virtual' }, simulated: true } as const
export const DEFAULT_MOCK_DEVICES: readonly Device[] = [
  { id: 'lichtschranke', name: 'Lichtschranke', kind: 'sensor', type: 'switch', value: false, ...VIRTUAL },
  { id: 'taster', name: 'Taster „Start“', kind: 'sensor', type: 'button', value: false, ...VIRTUAL },
  { id: 'weitere-objekte', name: 'Weitere Objekte', kind: 'sensor', type: 'switch', value: true, ...VIRTUAL },
  { id: 'fuellstand', name: 'Füllstand Kiste', kind: 'sensor', type: 'number', value: 0, unit: 'Stk', min: 0, max: 10, ...VIRTUAL },
  { id: 'lampe', name: 'Signallampe grün', kind: 'actuator', type: 'lamp', value: false, ...VIRTUAL },
  { id: 'lampe-rot', name: 'Signallampe rot', kind: 'actuator', type: 'lamp', value: false, ...VIRTUAL },
  { id: 'foerderband', name: 'Förderband', kind: 'actuator', type: 'conveyor', value: false, ...VIRTUAL },
  // Zellen-Geräte (im echten Backend gespiegelt aus der Zellen-Sitzung, hier nur nachgespielt)
  { id: 'zelle-maschine-fertig', name: 'Zelle: Maschine fertig', kind: 'sensor', type: 'switch', value: false, ...VIRTUAL },
  { id: 'zelle-cnc-maschine', name: 'Zelle: CNC-Maschine', kind: 'actuator', type: 'machine', value: false, ...VIRTUAL },
  { id: 'zelle-ampel-rot', name: 'Zelle: Ampel rot', kind: 'actuator', type: 'lamp', value: false, ...VIRTUAL },
  { id: 'zelle-ampel-gruen', name: 'Zelle: Ampel grün', kind: 'actuator', type: 'lamp', value: false, ...VIRTUAL },
]

const DEVICE_NODE_TYPES = new Set<WorkflowNode['type']>(['waitSensor', 'condition', 'setActuator'])

/** ID aus dem Namen wie im Backend: Umlaute ersetzen, sonst nur a–z, 0–9 und Bindestrich. */
export function slugify(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'geraet'
}

type Cursor = { nodeId: string; enteredAt: number; attempt: number; attemptStartedAt: number; pendingSend: boolean }
type RunState = { run: Run; doc: WorkflowDocument; cursor: Cursor | null; pausedAt: number | null; stepping: boolean }

export function compare(actual: DeviceValue | undefined, operator: ComparisonOperator, expected: DeviceValue): boolean {
  if (actual === undefined) return false
  switch (operator) {
    case 'eq':
      return actual === expected
    case 'neq':
      return actual !== expected
    case 'gt':
      return Number(actual) > Number(expected)
    case 'gte':
      return Number(actual) >= Number(expected)
    case 'lt':
      return Number(actual) < Number(expected)
    case 'lte':
      return Number(actual) <= Number(expected)
  }
}

const clone = <T>(value: T): T => structuredClone(value)

export function createMockClient(options: MockOptions = {}): ApiClient {
  const now = options.now ?? (() => Date.now())
  const promptDurationMs = options.promptDurationMs ?? 3000
  const iso = (t: number) => new Date(t).toISOString()
  const sqliteTimestamp = (t: number) => iso(t).slice(0, 19).replace('T', ' ')

  const devices = new Map(DEFAULT_MOCK_DEVICES.map((d) => [d.id, clone(d)]))
  const skills: Skill[] = []
  const workflows = new Map<string, Workflow>()
  const runs = new Map<string, RunState>()
  let nextSkillId = 1
  let nextWorkflowId = 1
  let nextRunId = 1

  /** Passwörter getrennt halten – wie das Backend gibt der Mock sie nie zurück */
  const passwords = new Map<string, string>()

  function workflowsUsing(deviceId: string): { id: string; name: string }[] {
    return [...workflows.values()]
      .filter((wf) => wf.nodes.some((n) => DEVICE_NODE_TYPES.has(n.type) && 'deviceId' in n.data && n.data.deviceId === deviceId))
      .map((wf) => ({ id: wf.id, name: wf.name }))
  }

  function toMockDevice(id: string, input: DeviceInput, old: Device | undefined): Device {
    const { password, ...config } = { password: undefined, ...input.config } as DeviceConfig & { password?: string | null }
    if (password) passwords.set(id, password)
    else if (!old || old.protocol !== input.config.protocol) passwords.delete(id)
    const publicConfig = input.config.protocol === 'virtual' ? config : { ...config, password_set: passwords.has(id) }
    const number = input.type === 'number'
    const keepValue = old !== undefined && old.type === input.type
    return {
      id,
      name: input.name.trim(),
      kind: DEVICE_TYPE_KIND[input.type],
      type: input.type,
      adapter: 'virtual',
      value: keepValue ? old.value : number ? (input.min ?? 0) : false,
      unit: number ? (input.unit ?? null) : null,
      min: number ? (input.min ?? null) : null,
      max: number ? (input.max ?? null) : null,
      protocol: input.config.protocol,
      config: publicConfig as DeviceConfig,
      simulated: true,
    }
  }

  // ----------------------------------------------------------------- Läufe
  function log(state: RunState, t: number, entry: Omit<RunLogEntry, 'ts'>) {
    state.run.log.push({ ts: iso(t), ...entry })
  }

  function finish(state: RunState, t: number, status: 'succeeded' | 'failed' | 'stopped', error: string | null) {
    state.run.status = status
    state.run.error = error
    state.run.finishedAt = iso(t)
    state.run.activeNodeId = null
    state.cursor = null
  }

  function enter(state: RunState, nodeId: string, t: number) {
    const node = state.doc.nodes.find((n) => n.id === nodeId)
    if (!node) {
      finish(state, t, 'failed', `Ziel-Block „${nodeId}“ existiert nicht.`)
      return
    }
    state.cursor = { nodeId, enteredAt: t, attempt: 0, attemptStartedAt: t, pendingSend: false }
    state.run.activeNodeId = nodeId
    if (state.stepping) {
      // Einzelschritt: am Eingang des nächsten Blocks anhalten – vor dem Senden eines Prompts.
      state.stepping = false
      state.run.status = 'paused'
      state.pausedAt = t
      state.cursor.pendingSend = node.type === 'prompt'
      log(state, t, { level: 'info', nodeId, apiStatus: null, durationMs: null, message: 'Einzelschritt: angehalten' })
      return
    }
    if (node.type === 'prompt') sendPrompt(state, node, t)
  }

  /** Pause beenden: Zeiten um die Pausendauer verschieben, ggf. ausstehenden Prompt senden. */
  function unpause(state: RunState, t: number) {
    const cursor = state.cursor
    if (cursor && state.pausedAt !== null) {
      const delta = t - state.pausedAt
      cursor.enteredAt += delta
      cursor.attemptStartedAt += delta
    }
    state.pausedAt = null
    state.run.status = 'running'
    if (cursor?.pendingSend) {
      cursor.pendingSend = false
      const node = state.doc.nodes.find((n) => n.id === cursor.nodeId)
      if (node?.type === 'prompt') sendPrompt(state, node, t)
    }
  }

  function requireStatus(state: RunState, status: Run['status'], action: string) {
    if (state.run.status !== status) {
      throw new ApiError(`Lauf kann nicht ${action} werden (Status: ${state.run.status}).`, 409)
    }
  }

  function sendPrompt(state: RunState, node: Extract<WorkflowNode, { type: 'prompt' }>, t: number) {
    state.run.credits.used += 1
    const attempt = (state.cursor?.attempt ?? 0) + 1
    log(state, t, {
      level: 'info',
      nodeId: node.id,
      apiStatus: 'running',
      durationMs: null,
      message: `Prompt an Dream-1 gesendet (Versuch ${attempt}): „${node.data.prompt}“`,
    })
  }

  function follow(state: RunState, node: WorkflowNode, handle: SourceHandle, t: number) {
    const edge = state.doc.edges.find((e) => e.source === node.id && e.sourceHandle === handle)
    if (!edge) {
      finish(state, t, 'failed', `Block „${node.id}“ hat keinen Ausgang „${handle}“.`)
      log(state, t, { level: 'error', nodeId: node.id, apiStatus: null, durationMs: null, message: state.run.error ?? '' })
      return
    }
    enter(state, edge.target, t)
  }

  /** Rückgabe true = Block wartet noch (Zeit oder Sensor). */
  function step(state: RunState, node: WorkflowNode, cursor: Cursor, t: number): boolean {
    switch (node.type) {
      case 'start':
        log(state, t, { level: 'info', nodeId: node.id, apiStatus: null, durationMs: null, message: 'Lauf gestartet' })
        follow(state, node, 'out', cursor.enteredAt)
        return false

      case 'prompt': {
        const elapsed = t - cursor.attemptStartedAt
        const timeoutMs = node.data.timeoutS * 1000
        if (promptDurationMs <= timeoutMs) {
          if (elapsed < promptDurationMs) return true
          const doneAt = cursor.attemptStartedAt + promptDurationMs
          log(state, doneAt, { level: 'info', nodeId: node.id, apiStatus: 'succeeded', durationMs: promptDurationMs, message: 'Dream-1 meldet Erfolg' })
          follow(state, node, 'out', doneAt)
          return false
        }
        if (elapsed < timeoutMs) return true
        const timedOutAt = cursor.attemptStartedAt + timeoutMs
        log(state, timedOutAt, { level: 'warn', nodeId: node.id, apiStatus: 'timeout', durationMs: timeoutMs, message: `Zeitlimit von ${node.data.timeoutS} s überschritten` })
        if (cursor.attempt < node.data.retries) {
          cursor.attempt += 1
          cursor.attemptStartedAt = timedOutAt
          sendPrompt(state, node, timedOutAt)
          return false
        }
        follow(state, node, 'error', timedOutAt)
        return false
      }

      case 'waitSensor': {
        if (compare(devices.get(node.data.deviceId)?.value, node.data.operator, node.data.value)) {
          log(state, t, { level: 'info', nodeId: node.id, apiStatus: null, durationMs: t - cursor.enteredAt, message: `Sensor „${node.data.deviceId}“ erfüllt` })
          follow(state, node, 'out', t)
          return false
        }
        if (node.data.timeoutS !== null && t - cursor.enteredAt >= node.data.timeoutS * 1000) {
          const at = cursor.enteredAt + node.data.timeoutS * 1000
          log(state, at, { level: 'warn', nodeId: node.id, apiStatus: 'timeout', durationMs: node.data.timeoutS * 1000, message: `Sensor „${node.data.deviceId}“: Zeitlimit überschritten` })
          follow(state, node, 'error', at)
          return false
        }
        return true
      }

      case 'condition': {
        const result = compare(devices.get(node.data.deviceId)?.value, node.data.operator, node.data.value)
        log(state, t, { level: 'info', nodeId: node.id, apiStatus: null, durationMs: null, message: `Bedingung ${result ? 'wahr' : 'nicht erfüllt (sonst)'}` })
        follow(state, node, result ? 'true' : 'false', cursor.enteredAt)
        return false
      }

      case 'setActuator': {
        const device = devices.get(node.data.deviceId)
        if (device) device.value = node.data.value
        log(state, t, { level: 'info', nodeId: node.id, apiStatus: null, durationMs: null, message: `Aktor „${node.data.deviceId}“ = ${String(node.data.value)}` })
        follow(state, node, 'out', cursor.enteredAt)
        return false
      }

      case 'wait': {
        const ms = node.data.seconds * 1000
        if (t - cursor.enteredAt < ms) return true
        log(state, cursor.enteredAt + ms, { level: 'info', nodeId: node.id, apiStatus: null, durationMs: ms, message: `${node.data.seconds} s gewartet` })
        follow(state, node, 'out', cursor.enteredAt + ms)
        return false
      }

      case 'end':
        log(state, t, { level: 'info', nodeId: node.id, apiStatus: null, durationMs: null, message: 'Lauf erfolgreich beendet' })
        finish(state, t, 'succeeded', null)
        return false
    }
  }

  function advance(state: RunState, t: number) {
    for (let i = 0; i < MAX_TRANSITIONS_PER_POLL; i++) {
      if (state.run.status !== 'running' || !state.cursor) return
      const cursor = state.cursor
      const node = state.doc.nodes.find((n) => n.id === cursor.nodeId)
      if (!node) {
        finish(state, t, 'failed', `Block „${cursor.nodeId}“ existiert nicht.`)
        return
      }
      if (step(state, node, cursor, t)) return
    }
    finish(state, t, 'failed', 'Endlosschleife ohne Wartezeit erkannt – Lauf abgebrochen.')
  }

  function getState(id: string): RunState {
    const state = runs.get(id)
    if (!state) throw new ApiError(`Lauf „${id}“ nicht gefunden.`, 404)
    return state
  }

  // ---------------------------------------------------------------- Skills
  function assertUniqueName(name: string, exceptId?: number) {
    if (skills.some((s) => s.name === name && s.id !== exceptId)) {
      throw new ApiError(`Ein Skill mit dem Namen „${name}“ existiert bereits.`, 409)
    }
  }

  function addSkill(input: SkillInput): Skill {
    assertUniqueName(input.name)
    const skill: Skill = {
      id: nextSkillId++,
      name: input.name,
      description: input.description,
      created_at: sqliteTimestamp(now()),
      status: input.status ?? 'Entwurf',
      fine_tuned_model: input.fine_tuned_model ?? null,
    }
    skills.push(skill)
    return skill
  }

  return {
    mode: 'mock',
    health: async () => ({ status: 'ok', service: 'mock' }),
    status: async () => ({
      version: 'mock',
      api_mode: 'mock',
      banner: 'SIMULIERTE API',
      dream_api_key_set: false,
      simulation_reachable: null,
      problems: [],
    }),

    listSkills: async () => clone(skills),
    createSkill: async (input) => clone(addSkill(input)),
    importSimulationSkills: async () => {
      for (const sim of MOCK_SIMULATION_SKILLS) {
        if (!skills.some((s) => s.name === sim.name)) addSkill(sim)
      }
      return clone(skills)
    },
    validateWorkflow: async (doc) => {
      const result = validateWorkflow(doc)
      return { valid: result.valid, issues: result.issues, creditsEstimate: estimateCredits(doc).maxPerPass }
    },
    updateSkill: async (id, input) => {
      const skill = skills.find((s) => s.id === id)
      if (!skill) throw new ApiError(`Skill ${id} nicht gefunden.`, 404)
      assertUniqueName(input.name, id)
      skill.name = input.name
      skill.description = input.description
      if (input.status !== undefined) skill.status = input.status
      if (input.fine_tuned_model !== undefined) skill.fine_tuned_model = input.fine_tuned_model
      return clone(skill)
    },

    // wie das Backend: zuletzt geänderte zuerst
    listWorkflows: async () =>
      [...workflows.values()]
        .reverse()
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
        .map(({ id, name, updated_at }) => ({ id, name, updated_at })),
    deleteWorkflow: async (id) => {
      if (!workflows.delete(id)) throw new ApiError(`Workflow „${id}“ nicht gefunden.`, 404)
    },
    getWorkflow: async (id) => {
      const wf = workflows.get(id)
      if (!wf) throw new ApiError(`Workflow „${id}“ nicht gefunden.`, 404)
      return clone(wf)
    },
    createWorkflow: async (doc) => {
      const wf: Workflow = { ...clone(doc), id: `wf-${nextWorkflowId++}`, updated_at: iso(now()) }
      workflows.set(wf.id, wf)
      return clone(wf)
    },
    updateWorkflow: async (id, doc) => {
      if (!workflows.has(id)) throw new ApiError(`Workflow „${id}“ nicht gefunden.`, 404)
      const wf: Workflow = { ...clone(doc), id, updated_at: iso(now()) }
      workflows.set(id, wf)
      return clone(wf)
    },

    startRun: async ({ workflowId, workflow }) => {
      const t = now()
      const state: RunState = {
        doc: clone(workflow),
        cursor: null,
        pausedAt: null,
        stepping: false,
        run: {
          id: `run-${nextRunId++}`,
          workflowId,
          status: 'running',
          activeNodeId: null,
          startedAt: iso(t),
          finishedAt: null,
          error: null,
          credits: { used: 0 },
          log: [],
        },
      }
      runs.set(state.run.id, state)
      const start = state.doc.nodes.find((n) => n.type === 'start')
      if (!start) finish(state, t, 'failed', 'Der Workflow hat keinen Start-Block.')
      else enter(state, start.id, t)
      advance(state, t)
      return clone(state.run)
    },
    getRun: async (id) => {
      const state = getState(id)
      advance(state, now())
      return clone(state.run)
    },
    stopRun: async (id) => {
      const state = getState(id)
      const t = now()
      advance(state, t)
      if (state.run.status === 'running' || state.run.status === 'paused') {
        log(state, t, { level: 'warn', nodeId: state.run.activeNodeId, apiStatus: 'stopped', durationMs: null, message: 'Lauf vom Nutzer gestoppt' })
        finish(state, t, 'stopped', null)
      }
      return clone(state.run)
    },
    pauseRun: async (id) => {
      const state = getState(id)
      const t = now()
      advance(state, t)
      requireStatus(state, 'running', 'pausiert')
      state.run.status = 'paused'
      state.pausedAt = t
      log(state, t, { level: 'info', nodeId: state.run.activeNodeId, apiStatus: null, durationMs: null, message: 'Lauf pausiert' })
      return clone(state.run)
    },
    resumeRun: async (id) => {
      const state = getState(id)
      const t = now()
      requireStatus(state, 'paused', 'fortgesetzt')
      log(state, t, { level: 'info', nodeId: state.run.activeNodeId, apiStatus: null, durationMs: null, message: 'Lauf fortgesetzt' })
      unpause(state, t)
      advance(state, t)
      return clone(state.run)
    },
    stepRun: async (id) => {
      const state = getState(id)
      const t = now()
      requireStatus(state, 'paused', 'im Einzelschritt ausgeführt')
      state.stepping = true
      unpause(state, t)
      advance(state, t)
      return clone(state.run)
    },

    listDevices: async () => [...devices.values()].map(clone),
    setDevice: async (id, value) => {
      const device = devices.get(id)
      if (!device) throw new ApiError(`Gerät „${id}“ nicht gefunden.`, 404)
      device.value = value
      return clone(device)
    },
    createDevice: async (input) => {
      const base = slugify(input.name)
      let id = base
      for (let n = 2; devices.has(id); n++) id = `${base}-${n}`
      const device = toMockDevice(id, input, undefined)
      devices.set(id, device)
      return clone(device)
    },
    updateDevice: async (id, input) => {
      const old = devices.get(id)
      if (!old) throw new ApiError(`Gerät „${id}“ nicht gefunden.`, 404)
      if (DEVICE_TYPE_KIND[input.type] !== old.kind && workflowsUsing(id).length > 0) {
        throw new ApiError(`„${id}“ wird in Workflows als ${old.kind === 'sensor' ? 'Sensor' : 'Aktor'} verwendet; Art kann nicht wechseln.`, 409)
      }
      const device = toMockDevice(id, input, old)
      devices.set(id, device)
      return clone(device)
    },
    deleteDevice: async (id) => {
      if (!devices.has(id)) throw new ApiError(`Gerät „${id}“ nicht gefunden.`, 404)
      const using = workflowsUsing(id)
      if (using.length > 0) {
        throw new ApiError(`Gerät „${id}“ wird in Workflows verwendet: ${using.map((w) => `„${w.name}“`).join(', ')}`, 409, 'conflict', using)
      }
      devices.delete(id)
      passwords.delete(id)
    },

    ...createCellsMock(now),
  }
}
