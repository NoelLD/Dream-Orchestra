import { Bot, Flag, GitBranch, Play, Radar, Timer, ToggleRight, type LucideIcon } from 'lucide-react'
import type { NodeDataOf, SourceHandle, WorkflowNodeType } from '@/api/contract'

export type BlockMeta<T extends WorkflowNodeType = WorkflowNodeType> = {
  type: T
  label: string
  description: string
  icon: LucideIcon
  /** Tailwind-Klassen: Akzentfarbe (Rand/Icon) – Text bleibt dunkel für Kontrast */
  accent: string
  iconBg: string
  outputs: SourceHandle[]
  hasInput: boolean
  defaultData: () => NodeDataOf<T>
}

export const BLOCKS: { [K in WorkflowNodeType]: BlockMeta<K> } = {
  start: {
    type: 'start',
    label: 'Start',
    description: 'Beginn des Ablaufs',
    icon: Play,
    accent: 'border-emerald-600',
    iconBg: 'bg-emerald-100 text-emerald-800',
    outputs: ['out'],
    hasInput: false,
    defaultData: () => ({}),
  },
  prompt: {
    type: 'prompt',
    label: 'Dream-1-Prompt',
    description: 'Anweisung an den Roboter',
    icon: Bot,
    accent: 'border-violet-600',
    iconBg: 'bg-violet-100 text-violet-800',
    outputs: ['out', 'error'],
    hasInput: true,
    defaultData: () => ({ prompt: '', skillId: null, timeoutS: 60, retries: 0 }),
  },
  waitSensor: {
    type: 'waitSensor',
    label: 'Warte auf Sensor',
    description: 'Wartet, bis ein Sensor einen Wert hat',
    icon: Radar,
    accent: 'border-amber-600',
    iconBg: 'bg-amber-100 text-amber-900',
    outputs: ['out', 'error'],
    hasInput: true,
    defaultData: () => ({ deviceId: '', operator: 'eq', value: true, timeoutS: null }),
  },
  setActuator: {
    type: 'setActuator',
    label: 'Aktor setzen',
    description: 'Schaltet Lampe oder Förderband',
    icon: ToggleRight,
    accent: 'border-sky-600',
    iconBg: 'bg-sky-100 text-sky-900',
    outputs: ['out'],
    hasInput: true,
    defaultData: () => ({ deviceId: '', value: true }),
  },
  wait: {
    type: 'wait',
    label: 'Warte (Zeit)',
    description: 'Feste Pause in Sekunden',
    icon: Timer,
    accent: 'border-slate-600',
    iconBg: 'bg-slate-200 text-slate-800',
    outputs: ['out'],
    hasInput: true,
    defaultData: () => ({ seconds: 2 }),
  },
  condition: {
    type: 'condition',
    label: 'Bedingung',
    description: 'Wenn Sensor …, dann A, sonst B',
    icon: GitBranch,
    accent: 'border-orange-600',
    iconBg: 'bg-orange-100 text-orange-900',
    outputs: ['true', 'false'],
    hasInput: true,
    defaultData: () => ({ deviceId: '', operator: 'eq', value: true }),
  },
  end: {
    type: 'end',
    label: 'Ende',
    description: 'Ablauf erfolgreich beenden',
    icon: Flag,
    accent: 'border-rose-600',
    iconBg: 'bg-rose-100 text-rose-900',
    outputs: [],
    hasInput: true,
    defaultData: () => ({}),
  },
}

export const BLOCK_ORDER: WorkflowNodeType[] = ['start', 'prompt', 'waitSensor', 'setActuator', 'wait', 'condition', 'end']

export const OPERATOR_LABELS = { eq: '=', neq: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤' } as const

export const DND_MIME = 'application/x-dreamorchestra-block'
