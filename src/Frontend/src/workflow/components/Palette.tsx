import { useReactFlow } from '@xyflow/react'
import { cn } from '@/lib/utils'
import { BLOCK_ORDER, BLOCKS, DND_MIME } from '../blocks'
import { useEditor } from '../store'

export function Palette() {
  const addBlock = useEditor((s) => s.addBlock)
  const { screenToFlowPosition } = useReactFlow()

  const addAtCenter = (type: (typeof BLOCK_ORDER)[number]) => {
    const rect = document.querySelector('[data-testid="canvas"]')?.getBoundingClientRect()
    const center = rect ? { x: rect.left + rect.width / 2 - 110, y: rect.top + rect.height / 2 - 30 } : { x: 0, y: 0 }
    addBlock(type, screenToFlowPosition(center))
  }

  return (
    <nav aria-label="Block-Palette" className="flex h-full flex-col gap-2 overflow-y-auto p-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Blöcke</h2>
      <p className="text-[11px] text-slate-600">Auf die Fläche ziehen oder mit Enter einfügen.</p>
      {BLOCK_ORDER.map((type) => {
        const meta = BLOCKS[type]
        const Icon = meta.icon
        return (
          <button
            key={type}
            type="button"
            draggable
            data-testid={`palette-${type}`}
            title={meta.description}
            aria-label={`Block ${meta.label} einfügen – ${meta.description}`}
            onDragStart={(event) => {
              event.dataTransfer.setData(DND_MIME, type)
              event.dataTransfer.effectAllowed = 'move'
            }}
            onClick={() => addAtCenter(type)}
            className={cn(
              'flex cursor-grab items-center gap-2 rounded-md border border-l-4 bg-white px-2 py-1.5 text-left text-slate-900 shadow-xs',
              'hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 active:cursor-grabbing',
              meta.accent,
            )}
          >
            <span className={cn('flex size-6 shrink-0 items-center justify-center rounded', meta.iconBg)}>
              <Icon className="size-3.5" aria-hidden />
            </span>
            <span className="min-w-0 text-sm font-medium leading-tight">{meta.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
