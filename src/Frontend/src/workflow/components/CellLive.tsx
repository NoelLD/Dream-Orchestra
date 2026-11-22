import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { LiveImage } from '@/cells/CellsView'

/** Live-Bild der Zelle neben dem Protokoll, solange eine Zellen-Sitzung läuft (Jury sieht Block, Kamera, Meldung zugleich). */
export function CellLive() {
  const session = useQuery({ queryKey: ['cell-session'], queryFn: () => api.getCellSession(), refetchInterval: 1000 })
  const current = session.data ?? null
  if (!current) return null
  return (
    <section aria-label="Live cell image" className="flex h-full min-h-0 w-[300px] shrink-0 flex-col border-l bg-slate-50 p-1.5">
      <div className="flex items-center justify-between px-1 pb-1 text-xs">
        <span className="font-semibold uppercase tracking-wide text-slate-600">Cell {current.cell}</span>
        <span className="text-slate-500">{current.busy ? `working: ${current.busy}` : 'ready'}</span>
      </div>
      <div className="min-h-0 flex-1 [&_img]:h-full [&_img]:aspect-auto [&_img]:object-contain">
        <LiveImage session={current} view="overview" />
      </div>
    </section>
  )
}
