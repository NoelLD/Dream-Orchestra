import { Handle, Position, type NodeProps } from '@xyflow/react'
import { AlertTriangle } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { cn } from '@/lib/utils'
import { BLOCKS, OPERATOR_LABELS } from '../blocks'
import type { FlowNode } from '../flow'
import { useEditor, useRunStore } from '../store'
import { HANDLE_LABELS } from '../validate'

function summary(node: FlowNode): string {
  switch (node.type) {
    case 'start':
    case 'end':
      return ''
    case 'prompt':
      return node.data.prompt.trim() === '' ? '(kein Prompt)' : `„${node.data.prompt}“`
    case 'waitSensor':
      return `${node.data.deviceId || '?'} ${OPERATOR_LABELS[node.data.operator]} ${String(node.data.value)}${node.data.timeoutS ? ` · max. ${node.data.timeoutS} s` : ''}`
    case 'condition':
      return `wenn ${node.data.deviceId || '?'} ${OPERATOR_LABELS[node.data.operator]} ${String(node.data.value)}`
    case 'setActuator':
      return `${node.data.deviceId || '?'} → ${String(node.data.value)}`
    case 'wait':
      return `${node.data.seconds} s`
  }
}

export function BlockNode(props: NodeProps<FlowNode>) {
  const { id, type, selected } = props
  const node = { id, type, data: props.data } as FlowNode
  const meta = BLOCKS[type]
  const Icon = meta.icon
  const runState = useRunStore((s) => (s.run?.activeNodeId === id ? s.run.status : null))
  const isActive = runState === 'running' || runState === 'paused'
  const isPaused = runState === 'paused'
  const issues = useEditor(useShallow((s) => s.issues.filter((i) => i.nodeId === id).map((i) => i.message)))
  const text = summary(node)
  const title = node.data.label?.trim() || meta.label

  return (
    <div
      data-testid={`block-${id}`}
      data-active={isActive || undefined}
      aria-label={`${meta.label}: ${title}${isActive ? ' (aktiv)' : ''}${issues.length ? ` – ${issues.length} Fehler` : ''}`}
      className={cn(
        'relative rounded-lg border-2 border-l-8 bg-white px-3 py-2 text-slate-900 shadow-sm transition-shadow',
        type === 'start' || type === 'end' ? 'w-[130px]' : 'w-[190px]',
        meta.accent,
        selected && 'ring-2 ring-slate-900 ring-offset-2',
        issues.length > 0 && 'border-red-600 ring-2 ring-red-600',
        isActive && !isPaused && 'animate-pulse ring-4 ring-blue-600 ring-offset-2 shadow-lg shadow-blue-300',
        isPaused && 'ring-4 ring-amber-500 ring-offset-2 shadow-lg shadow-amber-200',
      )}
    >
      {meta.hasInput && <Handle type="target" position={Position.Left} className="!size-3 !border-2 !border-white !bg-slate-700" />}

      <div className="flex items-center gap-2">
        <span className={cn('flex size-7 shrink-0 items-center justify-center rounded-md', meta.iconBg)}>
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{title}</div>
          {title !== meta.label && <div className="text-[11px] text-slate-600">{meta.label}</div>}
        </div>
        {isActive && (
          <span className={cn('ml-auto rounded px-1.5 py-0.5 text-[10px] font-bold', isPaused ? 'bg-amber-400 text-black' : 'bg-blue-600 text-white')}>
            {isPaused ? 'PAUSE' : 'AKTIV'}
          </span>
        )}
      </div>

      {text && <p className="mt-1 line-clamp-2 text-xs text-slate-700">{text}</p>}

      {issues.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-[11px] font-medium text-red-700">
          {issues.map((m) => (
            <li key={m} className="flex gap-1">
              <AlertTriangle className="mt-px size-3 shrink-0" aria-hidden />
              {m}
            </li>
          ))}
        </ul>
      )}

      {meta.outputs.map((handle, index) => {
        const top = `${((index + 1) / (meta.outputs.length + 1)) * 100}%`
        const isError = handle === 'error' || handle === 'false'
        return (
          <div key={handle}>
            <Handle
              id={handle}
              type="source"
              position={Position.Right}
              style={{ top }}
              aria-label={`Ausgang ${HANDLE_LABELS[handle]}`}
              className={cn('!size-3 !border-2 !border-white', isError ? '!bg-red-600' : '!bg-emerald-600')}
            />
            {meta.outputs.length > 1 && (
              <span
                className={cn('pointer-events-none absolute -right-1 translate-x-full -translate-y-1/2 pl-2 text-[10px] font-semibold', isError ? 'text-red-700' : 'text-emerald-800')}
                style={{ top }}
              >
                {HANDLE_LABELS[handle]}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
