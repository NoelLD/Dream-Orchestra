/**
 * TESTMODUS für Zellen-Leitstand, Roboter und Fine-Tune-Ergebnisse. Spielt den Simulationsdienst nach
 * (src/Simulation/README.md, "Zellen-Experimente"); alle Daten sind erfunden und als Testdaten gekennzeichnet.
 */
import type { ApiClient, Cell, CellAction, CellResults, CellSession, CheckpointPolicy, Robot } from './contract'
import { ApiError } from './realClient'

type CellsApi = Pick<
  ApiClient,
  | 'listCells'
  | 'startCellSession'
  | 'getCellSession'
  | 'cellAction'
  | 'cellTask'
  | 'endCellSession'
  | 'cellFrameUrl'
  | 'listRobots'
  | 'getCellResults'
  | 'getCheckpointPolicy'
>

export const MOCK_CELLS: readonly Cell[] = [
  {
    cell: 'conveyor',
    tasks: [
      { task: 'sort_round', arm: 'right', prompt: 'put the round part from the conveyor in the green box' },
      { task: 'sort_cube', arm: 'left', prompt: 'put the metal cube from the conveyor in the blue box' },
    ],
  },
  {
    cell: 'cnc',
    tasks: [
      { task: 'cnc_load', arm: 'left', prompt: 'put the metal block on the machine tray' },
      { task: 'cnc_unload', arm: 'right', prompt: 'put the finished part in the green box' },
    ],
  },
]

const TASK_MS = 4000

const scenes = (pattern: string) =>
  [...pattern].map((c): [string, boolean, string] =>
    c === 's' ? ['success', false, 'success'] : c === 'd' ? ['dropped', true, 'timeout_dropped'] : ['no_grasp', false, 'timeout_no_grasp'],
  )

export const MOCK_POLICY: CheckpointPolicy = {
  robot: 'yam-sim',
  generated_at: '2026-11-22T00:00:00 (TESTDATEN)',
  rows: [
    {
      skill: 'cnc_load',
      name: 'Load CNC (Testdaten)',
      scope: 'cell',
      n: 10,
      base: { label: 'beta-main', name: 'Basis', k: 3 },
      checkpoint: { label: 'ft-main', name: 'Fine-tune c500', k: 7, note: 'nur in den Zellen' },
      controller: { name: 'Referenz-Controller (geskriptet)', k: 10, reason: 'Testdaten' },
      rejected: [{ label: 'ft-lr3-main', name: 'Fine-tune, lr 3e-5', k: 1, total: 20, reason: 'Testdaten' }],
    },
    {
      skill: 'pick-banana',
      name: 'Banane greifen (Testdaten)',
      scope: 'outside',
      n: 20,
      base: { label: 'beta', name: 'Basis', k: 6 },
      checkpoint: { label: 'beta', name: 'Basis', k: 6, note: 'Standard' },
      controller: { name: 'Dream-1 beta (Basis)', k: 6, reason: 'Testdaten' },
      rejected: [{ label: 'ft-main', name: 'Zellen-Fine-Tune', k: 0, total: 0, reason: 'Vergessen (Testdaten)' }],
    },
  ],
}

export const MOCK_RESULTS: CellResults = {
  generated_at: '2026-11-22T00:00:00',
  base: 'beta-main',
  tasks: ['sort_round', 'cnc_load'],
  task_names: { sort_round: 'Sort round part', cnc_load: 'Load CNC' },
  models: [
    {
      label: 'beta-main', name: 'Basis (Testdaten)', what: 'ohne Fine-Tune', prereg: true, k: 3, lo: 0.1, hi: 0.6, contact: 2,
      buckets: { success: 3, dropped: 2, no_grasp: 5 }, tasks: { sort_round: 1, cnc_load: 2 }, scenes: scenes('sdnnnssdnn'),
    },
    {
      label: 'ft-main', name: 'Fine-Tune (Testdaten)', what: 'Zellen-Vorführungen', prereg: true, k: 7, lo: 0.4, hi: 0.9, contact: 3,
      buckets: { success: 7, dropped: 1, no_grasp: 2 }, tasks: { sort_round: 3, cnc_load: 4 }, scenes: scenes('ssnsdssssn'),
      win: 5, loss: 1, p: 0.22,
    },
  ],
  spend: { jobs: [{ name: 'yam-cells-test', status: 'succeeded', usd: 100 }], evals: { 'ft-main': 1.5 }, credit: 1000 },
  queue: [{ label: 'beta-main2', name: 'Basis, zweiter Lauf (Testdaten)', eta: '~12:00', done: false }],
  public_url: '',
}

export const MOCK_ROBOTS: readonly Robot[] = [
  {
    name: 'yam-sim',
    description: 'Zwei YAM-Arme in der Simulation (Testdaten)',
    embodiment: 'yam-sim',
    skills: ['pick-banana', 'pick-apple'],
    fine_tuned_model: 'dream-1-ft:test-yam-cells',
    finetune_jobs: [
      {
        job_id: 'ftj_test', status: 'succeeded', dataset: 'cells-test', suffix: 'yam-cells-test', steps: 500,
        price_usd: 100, fine_tuned_model: 'dream-1-ft:test-yam-cells', created_at: '2026-11-22T00:00:00Z',
      },
    ],
  },
]

const frame = (view: string, cell: string, tick: number) =>
  'data:image/svg+xml,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#e2e8f0"/>` +
      `<text x="320" y="170" font-family="sans-serif" font-size="28" text-anchor="middle" fill="#475569">TESTMODUS: ${cell}</text>` +
      `<text x="320" y="210" font-family="sans-serif" font-size="16" text-anchor="middle" fill="#64748b">${view} · Bild ${tick}</text></svg>`,
  )

export function createCellsMock(now: () => number): CellsApi {
  let session: (CellSession & { taskEndsAt?: number; startedAt: number }) | null = null

  function advance() {
    if (!session?.busy || session.taskEndsAt === undefined || now() < session.taskEndsAt) return
    const task = session.busy
    session.busy = null
    session.taskEndsAt = undefined
    session.last_result = { task, seed: 1000, passed: true, reason: 'placed (Testdaten)' }
    if (session.sensors && task === 'cnc_load') session.sensors.raw_part_on_tray = true
    event(`Prüfung ${task}: bestanden (Testdaten)`, true)
  }

  function event(text: string, gate?: boolean) {
    if (!session) return
    session.events = [...session.events, { t: Math.round((now() - session.startedAt) / 100) / 10, text, ...(gate === undefined ? {} : { gate }) }].slice(-20)
  }

  function active() {
    if (!session) throw new ApiError('Keine Zellen-Sitzung (Testmodus).', 409, 'no_session')
    return session
  }

  return {
    listCells: async () => structuredClone([...MOCK_CELLS]),
    startCellSession: async (cell) => {
      if (!MOCK_CELLS.some((c) => c.cell === cell)) throw new ApiError(`Unbekannte Zelle „${cell}“.`, 404, 'unknown_cell')
      const cnc = cell === 'cnc'
      session = {
        cell,
        status: 'running',
        busy: null,
        startedAt: now(),
        sim_seconds: 0,
        sensors: cnc
          ? { door_open: false, door_closed: true, tray_out: true, raw_part_on_tray: false, finished_part_on_tray: false, machine_running: false, stack_light: null, cycles: 0 }
          : { belt_on: false, auto: false, parts_on_belt: 3 },
        events: [],
      }
      event(`Sitzung ${cell} gestartet (Testmodus)`)
    },
    getCellSession: async () => {
      if (!session) return null
      advance()
      session.sim_seconds = Math.round((now() - session.startedAt) / 100) / 10
      const { taskEndsAt: _end, startedAt: _start, ...publicState } = session
      return structuredClone(publicState)
    },
    cellAction: async (action: CellAction) => {
      const s = active()
      const sensors = s.sensors ?? {}
      if (action === 'door_open' || action === 'door_close') {
        sensors.door_open = action === 'door_open'
        sensors.door_closed = action === 'door_close'
      } else if (action === 'belt_on' || action === 'belt_off') sensors.belt_on = action === 'belt_on'
      else if (action.startsWith('light_')) sensors.stack_light = action === 'light_off' ? null : action.slice(6)
      s.sensors = sensors
      event(`Aktion: ${action}`)
    },
    cellTask: async (task) => {
      const s = active()
      advance()
      const cell = MOCK_CELLS.find((c) => c.tasks.some((t) => t.task === task))
      if (cell?.cell !== s.cell) throw new ApiError(`Task „${task}“ gehört nicht zu dieser Zelle.`, 400, 'wrong_cell')
      if (s.busy) throw new ApiError(`Zelle ist beschäftigt (${s.busy}).`, 409, 'busy')
      s.busy = task
      s.taskEndsAt = now() + TASK_MS
      event(`Task ${task} gestartet (Testmodus)`)
    },
    endCellSession: async () => {
      session = null
    },
    cellFrameUrl: (view, tick) => frame(view, session?.cell ?? 'keine Sitzung', tick),
    listRobots: async () => structuredClone([...MOCK_ROBOTS]),
    getCellResults: async () => structuredClone(MOCK_RESULTS),
    getCheckpointPolicy: async () => structuredClone(MOCK_POLICY),
  }
}
